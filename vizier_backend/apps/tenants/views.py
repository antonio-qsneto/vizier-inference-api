"""
Views for tenants app.
"""

from datetime import timedelta
import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.billing_url_validation import BillingRedirectURLError, validate_redirect_url
from apps.accounts.models import User, UserNotice, UserSubscription
from apps.accounts.permissions import CanManageClinicBilling, CanManageClinicTeam
from apps.accounts.rbac import RBACRole, resolve_effective_role
from apps.accounts.serializers import UserSerializer
from apps.audit.services import AuditService

from .billing import (
    cancel_clinic_subscription_at_period_end,
    ClinicBillingConfigurationError,
    ClinicBillingProviderError,
    apply_subscription_payload,
    construct_webhook_event,
    count_doctor_seats,
    create_checkout_session,
    create_checkout_session_for_new_clinic_owner,
    create_customer_portal_session,
    ensure_owner_membership,
    is_stripe_billing_enabled,
    list_clinic_billing_plans,
    record_and_process_webhook_event,
    retrieve_checkout_session,
    retrieve_subscription,
    update_subscription_price,
)
from .emails import send_doctor_invitation_email
from .models import Clinic, DoctorInvitation, Membership
from .serializers import (
    ClinicBillingCheckoutSerializer,
    ClinicBillingPortalSerializer,
    ClinicBillingSyncSerializer,
    ClinicDoctorSerializer,
    ClinicSerializer,
    DoctorInvitationCreateSerializer,
    DoctorInvitationSerializer,
)

logger = logging.getLogger(__name__)


def _clinic_required_response() -> Response:
    return Response(
        {'error': 'User must belong to a clinic'},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _billing_error_response(exc: Exception) -> Response:
    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _is_clinic_subscription_ended(clinic: Clinic) -> bool:
    if clinic.account_status != Clinic.ACCOUNT_STATUS_CANCELED:
        return False
    if clinic.stripe_current_period_end:
        return clinic.stripe_current_period_end <= timezone.now()
    return bool(clinic.canceled_at and not clinic.stripe_subscription_id and not clinic.cancel_at_period_end)


def _has_active_individual_paid_subscription(user: User) -> bool:
    subscription = UserSubscription.objects.filter(user=user).first()
    if not subscription:
        return False

    if subscription.plan not in {
        UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
        UserSubscription.PLAN_INDIVIDUAL_ANNUAL,
    }:
        return False

    return subscription.has_active_access()


def _is_clinic_account_user(user: User) -> bool:
    effective_role = resolve_effective_role(user)
    if effective_role in {RBACRole.CLINIC_ADMIN, RBACRole.CLINIC_DOCTOR}:
        return True
    if getattr(user, 'clinic_id', None):
        return True
    if getattr(user, 'role', None) in {'CLINIC_ADMIN', 'CLINIC_DOCTOR'}:
        return True
    return False


class ClinicViewSet(viewsets.ModelViewSet):
    """ViewSet for Clinic model."""

    queryset = Clinic.objects.all()
    serializer_class = ClinicSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in {'list', 'retrieve'}:
            if resolve_effective_role(self.request.user) == RBACRole.CLINIC_DOCTOR:
                return ClinicDoctorSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        """Filter clinics by user."""
        user = self.request.user
        if user.clinic:
            return Clinic.objects.filter(id=user.clinic.id)
        if user.is_staff:
            return Clinic.objects.all()
        return Clinic.objects.none()

    def create(self, request, *args, **kwargs):
        """
        Create a clinic and attach the requesting user as owner/admin.
        """
        if request.user.clinic_id:
            return Response(
                {'error': 'User already belongs to a clinic'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Clinic.objects.filter(owner=request.user).exists():
            return Response(
                {'error': 'User already owns a clinic'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if _has_active_individual_paid_subscription(request.user):
            return Response(
                {
                    'detail': (
                        'Usuários com assinatura individual ativa não podem criar clínica. '
                        'Cancele o plano individual e aguarde o fim do ciclo para prosseguir.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {
                    'detail': (
                        'A criação direta de clínica foi desativada. '
                        'Finalize o checkout de assinatura para criar a clínica.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            clinic = serializer.save(
                owner=request.user,
                plan_type=Clinic.PLAN_TYPE_CLINIC,
                subscription_plan=Clinic.SUBSCRIPTION_PLAN_FREE,
                account_status=Clinic.ACCOUNT_STATUS_CANCELED,
                seat_limit=0,
            )

            request.user.clinic = clinic
            request.user.role = 'CLINIC_ADMIN'
            request.user.save(update_fields=['clinic', 'role', 'updated_at'])

            Membership.objects.get_or_create(
                account=clinic,
                user=request.user,
                defaults={'role': Membership.ROLE_ADMIN},
            )

            AuditService.log_action(
                clinic=clinic,
                action='CLINIC_CREATED',
                user=request.user,
                resource_id=str(clinic.id),
                details={'name': clinic.name},
            )

        response_serializer = self.get_serializer(clinic)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, CanManageClinicBilling])
    def billing_plans(self, request):
        clinic = request.user.clinic
        if not clinic:
            return _clinic_required_response()

        return Response(
            {
                'plans': list_clinic_billing_plans(),
                'current_plan': clinic.subscription_plan,
                'account_status': clinic.account_status,
                'seat_limit': clinic.get_seat_limit(),
                'seat_used': clinic.get_seat_usage(),
                'billing_enabled': is_stripe_billing_enabled(),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def billing_checkout(self, request):
        if not is_stripe_billing_enabled():
            return Response(
                {'detail': 'Stripe billing is disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        clinic = request.user.clinic
        effective_role = resolve_effective_role(request.user)

        if clinic and effective_role != RBACRole.CLINIC_ADMIN:
            return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if not clinic and effective_role != RBACRole.INDIVIDUAL:
            return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if clinic and _is_clinic_subscription_ended(clinic):
            return Response(
                {'detail': 'Clinic subscription has already ended and billing features are disabled'},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = ClinicBillingCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        success_url = payload.get('success_url') or (
            'http://localhost:3000/clinic?billing=success&session_id={CHECKOUT_SESSION_ID}'
        )
        cancel_url = payload.get('cancel_url') or 'http://localhost:3000/clinic?billing=cancel'
        requested_quantity = payload.get('quantity')
        try:
            success_url = validate_redirect_url(success_url, field_name='success_url')
            cancel_url = validate_redirect_url(cancel_url, field_name='cancel_url')
        except BillingRedirectURLError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if clinic:
                if clinic.stripe_subscription_id and clinic.account_status in {
                    Clinic.ACCOUNT_STATUS_ACTIVE,
                    Clinic.ACCOUNT_STATUS_PAST_DUE,
                }:
                    quantity = clinic.get_seat_limit()
                    if quantity < 1:
                        return Response(
                            {'detail': 'At least one doctor is required to keep clinic billing active'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    seat_usage = count_doctor_seats(clinic)
                    if quantity < seat_usage:
                        return Response(
                            {
                                'detail': (
                                    f'Seat quantity ({quantity}) cannot be lower than '
                                    f'active doctors ({seat_usage})'
                                )
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    updated_subscription_payload, price_id = update_subscription_price(
                        clinic=clinic,
                        plan_id=payload['plan_id'],
                        quantity=quantity,
                    )
                    apply_subscription_payload(
                        clinic=clinic,
                        stripe_subscription_payload=updated_subscription_payload,
                        fallback_plan_id=payload['plan_id'],
                    )
                    AuditService.log_action(
                        clinic=clinic,
                        action='BILLING_SUBSCRIPTION_UPDATED',
                        user=request.user,
                        details={
                            'plan_id': payload['plan_id'],
                            'quantity': quantity,
                        },
                    )

                    return Response(
                        {
                            'mode': 'subscription_updated',
                            'detail': 'Clinic subscription updated successfully',
                            'plan': clinic.subscription_plan,
                            'account_status': clinic.account_status,
                            'seat_limit': clinic.get_seat_limit(),
                            'seat_used': clinic.get_seat_usage(),
                            'stripe_price_id': price_id,
                        },
                        status=status.HTTP_200_OK,
                    )

                checkout_session, price_id, quantity = create_checkout_session(
                    clinic=clinic,
                    initiated_by_user_id=request.user.id,
                    plan_id=payload['plan_id'],
                    success_url=success_url,
                    cancel_url=cancel_url,
                    requested_quantity=requested_quantity,
                )
            else:
                if _has_active_individual_paid_subscription(request.user):
                    return Response(
                        {
                            'detail': (
                                'Usuários com assinatura individual ativa não podem criar clínica. '
                                'Cancele o plano individual e aguarde o fim do ciclo para prosseguir.'
                            )
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                clinic_name = str(payload.get('clinic_name') or '').strip()
                if not clinic_name:
                    return Response(
                        {'detail': 'clinic_name is required when creating a clinic subscription'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                checkout_session, price_id, quantity = create_checkout_session_for_new_clinic_owner(
                    owner_email=request.user.email,
                    owner_user_id=request.user.id,
                    plan_id=payload['plan_id'],
                    success_url=success_url,
                    cancel_url=cancel_url,
                    clinic_name=clinic_name,
                    cnpj=str(payload.get('cnpj') or '').strip(),
                    requested_quantity=requested_quantity,
                )
        except (ClinicBillingConfigurationError, ClinicBillingProviderError) as exc:
            return _billing_error_response(exc)

        if clinic:
            AuditService.log_action(
                clinic=clinic,
                action='BILLING_CHECKOUT_CREATED',
                user=request.user,
                resource_id=str(checkout_session.get('id') or ''),
                details={
                    'plan_id': payload['plan_id'],
                    'quantity': quantity,
                },
            )
        return Response(
            {
                'checkout_url': checkout_session.get('url'),
                'checkout_session_id': checkout_session.get('id'),
                'stripe_price_id': price_id,
                'quantity': quantity,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, CanManageClinicBilling])
    def billing_portal(self, request):
        if not is_stripe_billing_enabled():
            return Response(
                {'detail': 'Stripe billing is disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        clinic = request.user.clinic
        if not clinic:
            return _clinic_required_response()
        if _is_clinic_subscription_ended(clinic):
            return Response(
                {'detail': 'Clinic subscription has already ended and billing features are disabled'},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = ClinicBillingPortalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return_url = serializer.validated_data.get('return_url') or 'http://localhost:3000/clinic'
        try:
            return_url = validate_redirect_url(return_url, field_name='return_url')
        except BillingRedirectURLError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not clinic.stripe_customer_id and clinic.stripe_subscription_id:
            try:
                payload = retrieve_subscription(clinic.stripe_subscription_id)
                apply_subscription_payload(clinic=clinic, stripe_subscription_payload=payload)
            except (ClinicBillingConfigurationError, ClinicBillingProviderError) as exc:
                return _billing_error_response(exc)

        if not clinic.stripe_customer_id:
            return Response(
                {'detail': 'No Stripe customer found for this clinic account'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            portal_session = create_customer_portal_session(
                customer_id=clinic.stripe_customer_id,
                return_url=return_url,
            )
        except (ClinicBillingConfigurationError, ClinicBillingProviderError) as exc:
            return _billing_error_response(exc)

        AuditService.log_action(
            clinic=clinic,
            action='BILLING_PORTAL_OPENED',
            user=request.user,
            details={'return_url': return_url},
        )
        return Response({'url': portal_session.get('url')}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def billing_sync(self, request):
        """
        Force synchronization after Stripe checkout return.

        This avoids stale UI when webhooks are delayed.
        """
        if not is_stripe_billing_enabled():
            return Response(
                {'detail': 'Stripe billing is disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        clinic = request.user.clinic
        effective_role = resolve_effective_role(request.user)
        if clinic and effective_role != RBACRole.CLINIC_ADMIN:
            return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        if not clinic and effective_role != RBACRole.INDIVIDUAL:
            return Response({'detail': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ClinicBillingSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        checkout_session_id = serializer.validated_data.get('checkout_session_id')
        fallback_plan_id = clinic.subscription_plan if clinic else Clinic.SUBSCRIPTION_PLAN_FREE

        if checkout_session_id:
            try:
                checkout_session = retrieve_checkout_session(checkout_session_id)
            except (ClinicBillingConfigurationError, ClinicBillingProviderError) as exc:
                return _billing_error_response(exc)

            if str(checkout_session.get('status') or '').strip().lower() != 'complete':
                return Response(
                    {'detail': 'Checkout session is not completed yet. Try again in a few seconds.'},
                    status=status.HTTP_409_CONFLICT,
                )

            metadata = checkout_session.get('metadata', {}) or {}
            initiated_by_user_id = metadata.get('initiated_by_user_id')
            if initiated_by_user_id and str(initiated_by_user_id) != str(request.user.id):
                return Response(
                    {'detail': 'Checkout session was initiated by a different user'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if clinic:
                clinic_id_from_session = metadata.get('clinic_id') or checkout_session.get(
                    'client_reference_id'
                )
                if not clinic_id_from_session:
                    return Response(
                        {'detail': 'Checkout session is missing clinic ownership metadata'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if str(clinic_id_from_session) != str(clinic.id):
                    return Response(
                        {'detail': 'Checkout session does not belong to this clinic account'},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            else:
                pending_owner_id = metadata.get('pending_clinic_owner_user_id')
                if not pending_owner_id:
                    return Response(
                        {'detail': 'Checkout session is missing clinic ownership metadata'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if str(pending_owner_id) != str(request.user.id):
                    return Response(
                        {'detail': 'Checkout session does not belong to this user account'},
                        status=status.HTTP_403_FORBIDDEN,
                    )

            stripe_customer_id = checkout_session.get('customer')
            stripe_subscription_id = checkout_session.get('subscription')
            fallback_plan_id = metadata.get('plan_id') or fallback_plan_id

            if not stripe_subscription_id:
                return Response(
                    {'detail': 'Checkout session is not completed yet. Try again in a few seconds.'},
                    status=status.HTTP_409_CONFLICT,
                )

            if not clinic:
                clinic_name = str(metadata.get('pending_clinic_name') or '').strip()
                clinic_cnpj = str(metadata.get('pending_clinic_cnpj') or '').strip()
                if not clinic_name:
                    return Response(
                        {'detail': 'Checkout session is missing clinic creation metadata'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                with transaction.atomic():
                    user_locked = User.objects.select_for_update().get(id=request.user.id)
                    if user_locked.clinic_id:
                        clinic = user_locked.clinic
                    else:
                        clinic = Clinic.objects.create(
                            name=clinic_name,
                            cnpj=clinic_cnpj or None,
                            owner=user_locked,
                            plan_type=Clinic.PLAN_TYPE_CLINIC,
                            subscription_plan=Clinic.SUBSCRIPTION_PLAN_FREE,
                            account_status=Clinic.ACCOUNT_STATUS_CANCELED,
                            seat_limit=0,
                        )
                        user_locked.clinic = clinic
                        user_locked.role = 'CLINIC_ADMIN'
                        user_locked.save(update_fields=['clinic', 'role', 'updated_at'])
                        Membership.objects.get_or_create(
                            account=clinic,
                            user=user_locked,
                            defaults={'role': Membership.ROLE_ADMIN},
                        )
                        AuditService.log_action(
                            clinic=clinic,
                            action='CLINIC_CREATED',
                            user=user_locked,
                            resource_id=str(clinic.id),
                            details={'name': clinic.name, 'source': 'billing_sync'},
                        )

            fields_to_update = []
            if stripe_customer_id and stripe_customer_id != clinic.stripe_customer_id:
                clinic.stripe_customer_id = stripe_customer_id
                fields_to_update.append('stripe_customer_id')
            if stripe_subscription_id and stripe_subscription_id != clinic.stripe_subscription_id:
                clinic.stripe_subscription_id = stripe_subscription_id
                fields_to_update.append('stripe_subscription_id')

            if fields_to_update:
                clinic.save(update_fields=fields_to_update + ['updated_at'])

        if not clinic or not clinic.stripe_subscription_id:
            return Response(
                {'detail': 'Checkout session is not completed yet. Try again in a few seconds.'},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            payload = retrieve_subscription(clinic.stripe_subscription_id)
            apply_subscription_payload(
                clinic=clinic,
                stripe_subscription_payload=payload,
                fallback_plan_id=fallback_plan_id,
            )
        except (ClinicBillingConfigurationError, ClinicBillingProviderError) as exc:
            return _billing_error_response(exc)

        AuditService.log_action(
            clinic=clinic,
            action='BILLING_SYNCED',
            user=request.user,
            details={
                'checkout_session_id': checkout_session_id,
                'plan': clinic.subscription_plan,
                'account_status': clinic.account_status,
                'seat_limit': clinic.get_seat_limit(),
                'seat_used': clinic.get_seat_usage(),
            },
        )
        return Response(
            {
                'detail': 'Clinic billing synchronized',
                'plan': clinic.subscription_plan,
                'account_status': clinic.account_status,
                'seat_limit': clinic.get_seat_limit(),
                'seat_used': clinic.get_seat_usage(),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, CanManageClinicBilling])
    def upgrade_seats(self, request):
        """Deprecated: manual seat changes were removed from clinic billing."""
        if not is_stripe_billing_enabled():
            return Response(
                {'detail': 'Stripe billing is disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        clinic = request.user.clinic
        if not clinic:
            return _clinic_required_response()
        if _is_clinic_subscription_ended(clinic):
            return Response(
                {'detail': 'Clinic subscription has already ended and billing features are disabled'},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {'detail': 'Atualização manual de assentos foi removida.'},
            status=status.HTTP_410_GONE,
        )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, CanManageClinicBilling])
    def change_seats(self, request):
        """Deprecated: manual seat changes were removed from clinic billing."""
        if not is_stripe_billing_enabled():
            return Response(
                {'detail': 'Stripe billing is disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        clinic = request.user.clinic
        if not clinic:
            return _clinic_required_response()
        if _is_clinic_subscription_ended(clinic):
            return Response(
                {'detail': 'Clinic subscription has already ended and billing features are disabled'},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {'detail': 'Atualização manual de assentos foi removida.'},
            status=status.HTTP_410_GONE,
        )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, CanManageClinicBilling])
    def cancel_subscription(self, request):
        """
        Cancel clinic subscription at period end.
        """
        if not is_stripe_billing_enabled():
            return Response(
                {'detail': 'Stripe billing is disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        clinic = request.user.clinic
        if not clinic:
            return _clinic_required_response()
        if _is_clinic_subscription_ended(clinic):
            return Response(
                {'detail': 'Clinic subscription has already ended and billing features are disabled'},
                status=status.HTTP_409_CONFLICT,
            )

        blockers = []
        active_doctors = count_doctor_seats(clinic)
        if active_doctors > 0:
            blockers.append(
                {
                    'code': 'CLINIC_DOCTORS_REMAIN',
                    'message': 'Remove all doctors before canceling clinic subscription.',
                }
            )
        if DoctorInvitation.objects.filter(clinic=clinic, status='PENDING').exists():
            blockers.append(
                {
                    'code': 'CLINIC_PENDING_INVITATIONS',
                    'message': 'Cancel all pending invitations before canceling clinic subscription.',
                }
            )

        co_admin_membership_exists = Membership.objects.filter(
            account=clinic,
            role=Membership.ROLE_ADMIN,
            user__is_active=True,
        ).exclude(user_id=clinic.owner_id).exists()
        co_admin_legacy_exists = User.objects.filter(
            clinic=clinic,
            role='CLINIC_ADMIN',
            is_active=True,
        ).exclude(id=clinic.owner_id).exists()
        if co_admin_membership_exists or co_admin_legacy_exists:
            blockers.append(
                {
                    'code': 'CLINIC_CO_ADMINS_REMAIN',
                    'message': 'Remove all co-admins before canceling clinic subscription.',
                }
            )

        if blockers:
            return Response(
                {'detail': blockers[0]['message'], 'blockers': blockers},
                status=status.HTTP_409_CONFLICT,
            )

        if not clinic.stripe_subscription_id:
            return Response(
                {'detail': 'No active Stripe subscription found for this clinic'},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            subscription_payload = cancel_clinic_subscription_at_period_end(clinic=clinic)
            apply_subscription_payload(
                clinic=clinic,
                stripe_subscription_payload=subscription_payload,
                fallback_plan_id=clinic.subscription_plan,
                event_created_at=timezone.now(),
            )
        except (ClinicBillingConfigurationError, ClinicBillingProviderError) as exc:
            return _billing_error_response(exc)

        AuditService.log_action(
            clinic=clinic,
            action='BILLING_SUBSCRIPTION_UPDATED',
            user=request.user,
            details={
                'mode': 'cancel_at_period_end',
                'account_status': clinic.account_status,
                'billing_period_end': (
                    clinic.stripe_current_period_end.isoformat()
                    if clinic.stripe_current_period_end
                    else None
                ),
            },
        )
        return Response(
            {
                'detail': 'Clinic subscription canceled. Access remains active until billing period end.',
                'account_status': Clinic.ACCOUNT_STATUS_CANCELED,
                'cancel_at_period_end': True,
                'billing_period_end': clinic.stripe_current_period_end,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, CanManageClinicBilling])
    def downgrade_to_individual(self, request):
        return Response(
            {
                'detail': (
                    'This endpoint is deprecated. Use /api/clinics/clinics/cancel_subscription/ '
                    'to cancel clinic billing at period end.'
                )
            },
            status=status.HTTP_410_GONE,
        )

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, CanManageClinicTeam])
    def team_members(self, request):
        clinic = request.user.clinic
        if not clinic:
            return _clinic_required_response()

        memberships = clinic.memberships.select_related('user').filter(user__is_active=True)
        if memberships.exists():
            admins = [m.user for m in memberships if m.role == Membership.ROLE_ADMIN]
            doctors = [m.user for m in memberships if m.role == Membership.ROLE_DOCTOR]
        else:
            admins = [clinic.owner]
            doctors = list(clinic.doctors.filter(is_active=True, role='CLINIC_DOCTOR'))

        return Response(
            {
                'admins': UserSerializer(admins, many=True).data,
                'doctors': UserSerializer(doctors, many=True).data,
                'seats_used': len(doctors),
                'seat_limit': clinic.get_seat_limit(),
                'account_status': clinic.account_status,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, CanManageClinicTeam])
    def invite(self, request):
        """
        Invite a doctor to the clinic.
        """
        serializer = DoctorInvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        clinic = request.user.clinic
        if not clinic:
            return _clinic_required_response()

        email = serializer.validated_data['email']

        if clinic.plan_type != Clinic.PLAN_TYPE_CLINIC:
            return Response(
                {'error': 'Invites are only available for clinic plan accounts'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if clinic.get_seat_usage() >= clinic.get_seat_limit():
            return Response(
                {
                    'error': (
                        'Seat limit reached for this clinic plan. '
                        'Remove a doctor before inviting another one.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(
            clinic=clinic,
            email=email,
            role='CLINIC_DOCTOR',
            is_active=True,
        ).exists():
            return Response(
                {'error': 'User is already a doctor in this clinic'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_user = User.objects.filter(email=email).first()
        if existing_user and _is_clinic_account_user(existing_user):
            return Response(
                {
                    'error': (
                        'This account already belongs to a clinic and cannot be invited '
                        'as a doctor.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if existing_user and _has_active_individual_paid_subscription(existing_user):
            return Response(
                {
                    'error': (
                        'This account already has an active individual subscription and '
                        'cannot be invited to a clinic.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                invitation, created = DoctorInvitation.objects.get_or_create(
                    clinic=clinic,
                    email=email,
                    defaults={
                        'invited_by': request.user,
                        'expires_at': timezone.now() + timedelta(days=7),
                    },
                )

                if not created:
                    if invitation.status == 'PENDING' and not invitation.is_expired():
                        return Response(
                            {'error': 'Invitation already sent to this email'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    invitation.status = 'PENDING'
                    invitation.invited_by = request.user
                    invitation.expires_at = timezone.now() + timedelta(days=7)
                    invitation.accepted_at = None
                    invitation.save(
                        update_fields=['status', 'invited_by', 'expires_at', 'accepted_at']
                    )

                send_doctor_invitation_email(invitation)

                AuditService.log_doctor_invite(clinic, request.user, email)

            response_serializer = DoctorInvitationSerializer(invitation)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        except Exception as exc:
            logger.error('Failed to invite doctor: %s', exc, exc_info=True)
            return Response(
                {'error': 'Failed to send invitation'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, CanManageClinicTeam])
    def doctors(self, request):
        """
        List active doctor users in the clinic.
        """
        clinic = request.user.clinic
        if not clinic:
            return _clinic_required_response()

        membership_doctor_ids = set(
            clinic.memberships.filter(
                role=Membership.ROLE_DOCTOR,
                user__is_active=True,
            ).values_list('user_id', flat=True)
        )
        legacy_doctor_ids = set(
            clinic.doctors.filter(
                is_active=True,
                role='CLINIC_DOCTOR',
            ).values_list('id', flat=True)
        )
        doctor_ids = membership_doctor_ids.union(legacy_doctor_ids)
        doctors = User.objects.filter(id__in=doctor_ids).order_by('id') if doctor_ids else User.objects.none()

        serializer = UserSerializer(doctors, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['delete'], permission_classes=[IsAuthenticated, CanManageClinicTeam])
    def remove_doctor(self, request):
        """
        Remove a doctor from the clinic.
        """
        clinic = request.user.clinic
        if not clinic:
            return _clinic_required_response()

        doctor_id = request.query_params.get('doctor_id')
        if not doctor_id:
            return Response(
                {'error': 'doctor_id parameter required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            doctor = User.objects.get(
                id=doctor_id,
                clinic=clinic,
                role='CLINIC_DOCTOR',
            )
        except User.DoesNotExist:
            return Response(
                {'error': 'Doctor not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            with transaction.atomic():
                clinic_locked = Clinic.objects.select_for_update().get(id=clinic.id)
                ensure_owner_membership(clinic_locked)

                current_doctors = count_doctor_seats(clinic_locked)
                if clinic_locked.stripe_subscription_id and current_doctors <= 1:
                    return Response(
                        {
                            'error': (
                                'At least one doctor seat must remain while the '
                                'clinic subscription is active'
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                membership = Membership.objects.filter(
                    account=clinic_locked,
                    user=doctor,
                    role=Membership.ROLE_DOCTOR,
                ).first()
                if not membership:
                    membership = Membership.objects.create(
                        account=clinic_locked,
                        user=doctor,
                        role=Membership.ROLE_DOCTOR,
                    )

                membership.delete()

                DoctorInvitation.objects.filter(
                    clinic=clinic_locked,
                    email=doctor.email,
                    status='ACCEPTED',
                ).update(status='REMOVED')

                doctor.clinic = None
                doctor.role = 'INDIVIDUAL'
                doctor.save(update_fields=['clinic', 'role', 'updated_at'])

                UserNotice.objects.create(
                    user=doctor,
                    type=UserNotice.TYPE_CLINIC_REMOVED,
                    title='Você foi desligado de uma clínica',
                    message=(
                        f'Seu acesso à clínica "{clinic_locked.name}" foi removido '
                        'por um administrador.'
                    ),
                    payload={
                        'clinic_id': str(clinic_locked.id),
                        'clinic_name': clinic_locked.name,
                        'removed_by_user_id': request.user.id,
                    },
                )

                AuditService.log_doctor_remove(clinic_locked, request.user, doctor)

            return Response({'status': 'Doctor removed'}, status=status.HTTP_200_OK)

        except (ClinicBillingConfigurationError, ClinicBillingProviderError) as exc:
            return _billing_error_response(exc)
        except Exception as exc:
            logger.error('Failed to remove doctor: %s', exc, exc_info=True)
            return Response(
                {'error': 'Failed to remove doctor'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def leave_clinic(self, request):
        """
        Allow clinic doctors to unlink themselves from the clinic.
        """
        if resolve_effective_role(request.user) != RBACRole.CLINIC_DOCTOR:
            return Response(
                {'error': 'Only clinic doctors can leave a clinic'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not request.user.clinic_id:
            return _clinic_required_response()

        try:
            with transaction.atomic():
                doctor = User.objects.select_for_update().get(id=request.user.id)
                if not doctor.clinic_id:
                    return _clinic_required_response()

                clinic = Clinic.objects.select_for_update().get(id=doctor.clinic_id)

                doctor_membership = Membership.objects.filter(
                    account=clinic,
                    user=doctor,
                    role=Membership.ROLE_DOCTOR,
                ).first()
                if doctor_membership:
                    doctor_membership.delete()
                elif Membership.objects.filter(
                    account=clinic,
                    user=doctor,
                    role=Membership.ROLE_ADMIN,
                ).exists():
                    return Response(
                        {'error': 'Clinic admins cannot leave through doctor self-unlink'},
                        status=status.HTTP_403_FORBIDDEN,
                    )

                DoctorInvitation.objects.filter(
                    clinic=clinic,
                    email=doctor.email,
                    status='ACCEPTED',
                ).update(status='REMOVED')

                doctor.clinic = None
                doctor.role = 'INDIVIDUAL'
                doctor.save(update_fields=['clinic', 'role', 'updated_at'])

                subscription, _ = UserSubscription.objects.get_or_create(user=doctor)
                subscription.plan = UserSubscription.PLAN_FREE
                subscription.status = UserSubscription.STATUS_INACTIVE
                subscription.stripe_subscription_id = None
                subscription.stripe_checkout_session_id = None
                subscription.stripe_price_id = None
                subscription.current_period_end = None
                subscription.billing_grace_until = None
                subscription.save()

                AuditService.log_action(
                    clinic=clinic,
                    action='DOCTOR_REMOVE',
                    user=doctor,
                    resource_id=str(doctor.id),
                    details={
                        'doctor_email': doctor.email,
                        'initiated_by': 'self',
                    },
                )

            return Response(
                {
                    'detail': 'Clinic link removed. You are now on the free individual plan.',
                    'new_role': 'INDIVIDUAL',
                    'clinic_id': None,
                    'subscription_plan': UserSubscription.PLAN_FREE,
                },
                status=status.HTTP_200_OK,
            )
        except (ClinicBillingConfigurationError, ClinicBillingProviderError) as exc:
            return _billing_error_response(exc)
        except Exception as exc:
            logger.error('Failed to leave clinic: %s', exc, exc_info=True)
            return Response(
                {'error': 'Failed to leave clinic'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DoctorInvitationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for DoctorInvitation model."""

    queryset = DoctorInvitation.objects.all()
    serializer_class = DoctorInvitationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter invitations by clinic."""
        user = self.request.user
        if user.clinic:
            return DoctorInvitation.objects.filter(clinic=user.clinic)
        return DoctorInvitation.objects.none()

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_invitations(self, request):
        """
        Get all pending invitations for the current user's email.
        """
        email = request.user.email
        invitations = DoctorInvitation.objects.filter(
            email=email,
            status='PENDING',
        )

        for invitation in invitations:
            if invitation.is_expired():
                invitation.status = 'EXPIRED'
                invitation.save(update_fields=['status'])

        invitations = invitations.filter(status='PENDING')
        serializer = self.get_serializer(invitations, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanManageClinicTeam])
    def cancel(self, request, pk=None):
        """
        Cancel a pending invitation sent by the current clinic admin.
        """
        clinic = request.user.clinic
        if not clinic:
            return _clinic_required_response()

        try:
            invitation = DoctorInvitation.objects.get(id=pk, clinic=clinic)
        except DoctorInvitation.DoesNotExist:
            return Response(
                {'error': 'Invitation not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if invitation.status != 'PENDING':
            return Response(
                {'error': f'Invitation is already {invitation.status}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if invitation.is_expired():
            invitation.status = 'EXPIRED'
            invitation.save(update_fields=['status'])
            return Response(
                {'error': 'Invitation has expired'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invitation.status = 'REMOVED'
        invitation.accepted_at = None
        invitation.save(update_fields=['status', 'accepted_at'])

        AuditService.log_doctor_invitation_cancel(clinic, request.user, invitation)

        response_serializer = self.get_serializer(invitation)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def accept(self, request, pk=None):
        """
        Accept a doctor invitation and synchronize Stripe seats when required.
        """
        try:
            invitation = DoctorInvitation.objects.select_related('clinic').get(id=pk)
        except DoctorInvitation.DoesNotExist:
            return Response(
                {'error': 'Invitation not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if invitation.email != request.user.email:
            return Response(
                {'error': 'Invitation is for a different email'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if invitation.status != 'PENDING':
            return Response(
                {'error': f'Invitation is already {invitation.status}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if invitation.is_expired():
            invitation.status = 'EXPIRED'
            invitation.save(update_fields=['status'])
            return Response(
                {'error': 'Invitation has expired'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.user.clinic and request.user.clinic != invitation.clinic:
            return Response(
                {'error': 'User already belongs to another clinic'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                clinic = Clinic.objects.select_for_update().get(id=invitation.clinic_id)
                ensure_owner_membership(clinic)

                if clinic.get_seat_usage() >= clinic.get_seat_limit():
                    return Response(
                        {
                            'error': (
                                'Seat limit reached for this clinic. Ask an admin to free a seat '
                                'before accepting this invitation.'
                            )
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                invitation.accept()

                request.user.clinic = clinic
                request.user.role = 'CLINIC_DOCTOR'
                request.user.save(update_fields=['clinic', 'role', 'updated_at'])

                membership, created = Membership.objects.get_or_create(
                    account=clinic,
                    user=request.user,
                    defaults={'role': Membership.ROLE_DOCTOR},
                )
                if not created and membership.role != Membership.ROLE_DOCTOR:
                    membership.role = Membership.ROLE_DOCTOR
                    membership.save(update_fields=['role', 'updated_at'])

                AuditService.log_action(
                    clinic=clinic,
                    action='DOCTOR_INVITE',
                    user=request.user,
                    resource_id=str(invitation.id),
                    details={'doctor_email': request.user.email},
                )

            response_serializer = self.get_serializer(invitation)
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except (ClinicBillingConfigurationError, ClinicBillingProviderError) as exc:
            return _billing_error_response(exc)
        except Exception as exc:
            logger.error('Failed to accept invitation: %s', exc, exc_info=True)
            return Response(
                {'error': 'Failed to accept invitation'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ClinicStripeWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not is_stripe_billing_enabled():
            return Response(
                {'detail': 'Stripe billing is disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        signature = request.META.get('HTTP_STRIPE_SIGNATURE')
        if not signature:
            return Response({'detail': 'Missing Stripe signature'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            event_payload = construct_webhook_event(payload=request.body, signature=signature)
            processed = record_and_process_webhook_event(event_payload)
        except (ClinicBillingConfigurationError, ClinicBillingProviderError) as exc:
            return _billing_error_response(exc)
        except Exception:
            logger.error('Failed to process clinic Stripe webhook', exc_info=True)
            return Response({'detail': 'Webhook processing failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {'status': 'ok', 'processed': bool(processed)},
            status=status.HTTP_200_OK,
        )
