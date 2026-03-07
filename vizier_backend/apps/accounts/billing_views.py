"""
Billing endpoints for Stripe checkout/portal/webhook.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .billing import (
    BillingConfigurationError,
    BillingProviderError,
    construct_webhook_event,
    create_checkout_session,
    create_customer_portal_session,
    extract_subscription_price_id,
    infer_plan_id_from_price_id,
    is_stripe_billing_enabled,
    list_individual_billing_plans,
    normalize_subscription_status,
    retrieve_checkout_session,
    retrieve_subscription,
    timestamp_to_datetime,
    update_subscription_plan,
)
from .models import User, UserSubscription
from .serializers import BillingCheckoutSerializer, BillingPortalSerializer

logger = logging.getLogger(__name__)


def _payload_get(payload, key, default=None):
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _resolve_subscription_for_checkout_completed(checkout_payload) -> UserSubscription | None:
    session_id = _payload_get(checkout_payload, 'id')
    metadata = _payload_get(checkout_payload, 'metadata', {}) or {}

    subscription = None
    if session_id:
        subscription = UserSubscription.objects.filter(
            stripe_checkout_session_id=session_id
        ).select_related('user').first()

    if subscription:
        return subscription

    user_id = metadata.get('user_id') or _payload_get(checkout_payload, 'client_reference_id')
    if user_id:
        user = User.objects.filter(id=user_id).first()
        if user:
            subscription, _ = UserSubscription.objects.get_or_create(user=user)
            return subscription

    customer_details = _payload_get(checkout_payload, 'customer_details', {}) or {}
    email = _payload_get(customer_details, 'email') or _payload_get(checkout_payload, 'customer_email')
    if email:
        user = User.objects.filter(email__iexact=email).first()
        if user:
            subscription, _ = UserSubscription.objects.get_or_create(user=user)
            return subscription

    return None


def _apply_subscription_payload(
    *,
    subscription: UserSubscription,
    stripe_subscription_payload,
    fallback_plan_id: str | None = None,
):
    stripe_status = _payload_get(stripe_subscription_payload, 'status')
    stripe_subscription_id = _payload_get(stripe_subscription_payload, 'id')
    stripe_customer_id = _payload_get(stripe_subscription_payload, 'customer')
    current_period_end = timestamp_to_datetime(
        _payload_get(stripe_subscription_payload, 'current_period_end')
    )
    price_id = extract_subscription_price_id(stripe_subscription_payload)
    inferred_plan = infer_plan_id_from_price_id(price_id)

    target_plan = inferred_plan or fallback_plan_id or subscription.plan
    if target_plan not in {
        UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
        UserSubscription.PLAN_INDIVIDUAL_ANNUAL,
    }:
        target_plan = subscription.plan or UserSubscription.PLAN_FREE

    subscription.plan = target_plan
    subscription.status = normalize_subscription_status(stripe_status)
    if stripe_subscription_id:
        subscription.stripe_subscription_id = stripe_subscription_id
    if stripe_customer_id:
        subscription.stripe_customer_id = stripe_customer_id
    if price_id:
        subscription.stripe_price_id = price_id
    subscription.current_period_end = current_period_end
    subscription.save()


def _handle_checkout_session_completed(event_payload):
    checkout_payload = _payload_get(_payload_get(event_payload, 'data', {}) or {}, 'object', {}) or {}
    subscription = _resolve_subscription_for_checkout_completed(checkout_payload)
    if not subscription:
        logger.warning('Stripe checkout.session.completed without matching local user subscription')
        return

    metadata = _payload_get(checkout_payload, 'metadata', {}) or {}
    plan_id = metadata.get('plan_id') or subscription.plan

    stripe_subscription_id = _payload_get(checkout_payload, 'subscription')
    stripe_customer_id = _payload_get(checkout_payload, 'customer')
    if stripe_customer_id:
        subscription.stripe_customer_id = stripe_customer_id
    if _payload_get(checkout_payload, 'id'):
        subscription.stripe_checkout_session_id = _payload_get(checkout_payload, 'id')

    if stripe_subscription_id:
        try:
            stripe_subscription_payload = retrieve_subscription(stripe_subscription_id)
            _apply_subscription_payload(
                subscription=subscription,
                stripe_subscription_payload=stripe_subscription_payload,
                fallback_plan_id=plan_id,
            )
            return
        except BillingProviderError:
            logger.warning(
                'Failed to retrieve Stripe subscription %s after checkout completion',
                stripe_subscription_id,
                exc_info=True,
            )

    subscription.plan = plan_id
    subscription.status = UserSubscription.STATUS_ACTIVE
    subscription.stripe_subscription_id = stripe_subscription_id
    subscription.save()


def _handle_subscription_lifecycle_event(event_payload):
    stripe_subscription_payload = _payload_get(_payload_get(event_payload, 'data', {}) or {}, 'object', {}) or {}
    stripe_subscription_id = _payload_get(stripe_subscription_payload, 'id')
    stripe_customer_id = _payload_get(stripe_subscription_payload, 'customer')

    subscription = None
    if stripe_subscription_id:
        subscription = UserSubscription.objects.filter(
            stripe_subscription_id=stripe_subscription_id
        ).first()
    if not subscription and stripe_customer_id:
        subscription = UserSubscription.objects.filter(
            stripe_customer_id=stripe_customer_id
        ).first()

    if not subscription:
        logger.warning(
            'Stripe subscription event without local mapping (subscription_id=%s, customer_id=%s)',
            stripe_subscription_id,
            stripe_customer_id,
        )
        return

    _apply_subscription_payload(
        subscription=subscription,
        stripe_subscription_payload=stripe_subscription_payload,
    )


def _process_stripe_event(event_payload):
    event_type = _payload_get(event_payload, 'type')
    if event_type == 'checkout.session.completed':
        _handle_checkout_session_completed(event_payload)
        return

    if event_type in {
        'customer.subscription.created',
        'customer.subscription.updated',
        'customer.subscription.deleted',
    }:
        _handle_subscription_lifecycle_event(event_payload)
        return


def _sync_subscription_from_checkout_session(subscription: UserSubscription) -> UserSubscription:
    checkout_session_id = subscription.stripe_checkout_session_id
    if not checkout_session_id:
        return subscription

    checkout_payload = retrieve_checkout_session(checkout_session_id)
    stripe_customer_id = _payload_get(checkout_payload, 'customer')
    stripe_subscription_id = _payload_get(checkout_payload, 'subscription')

    fields_to_update = []
    if stripe_customer_id and stripe_customer_id != subscription.stripe_customer_id:
        subscription.stripe_customer_id = stripe_customer_id
        fields_to_update.append('stripe_customer_id')
    if stripe_subscription_id and stripe_subscription_id != subscription.stripe_subscription_id:
        subscription.stripe_subscription_id = stripe_subscription_id
        fields_to_update.append('stripe_subscription_id')

    if fields_to_update:
        subscription.save(update_fields=fields_to_update + ['updated_at'])

    if stripe_subscription_id:
        stripe_subscription_payload = retrieve_subscription(stripe_subscription_id)
        _apply_subscription_payload(
            subscription=subscription,
            stripe_subscription_payload=stripe_subscription_payload,
            fallback_plan_id=subscription.plan,
        )
        subscription.refresh_from_db()

    return subscription


def _validate_plan_change_password(user: User, password: str | None) -> str | None:
    if not password:
        return 'Current password is required to confirm plan change'
    if not user.has_usable_password():
        return (
            'Password confirmation is unavailable for this account. '
            'Use development login or manage changes in Stripe portal.'
        )
    if not user.check_password(password):
        return 'Invalid password confirmation'
    return None


class BillingPlansView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                'plans': list_individual_billing_plans(),
                'current_plan': request.user.get_effective_subscription_plan(),
                'billing_enabled': is_stripe_billing_enabled(),
            },
            status=status.HTTP_200_OK,
        )


class BillingCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not is_stripe_billing_enabled():
            return Response(
                {'detail': 'Stripe billing is disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if request.user.clinic:
            return Response(
                {'detail': 'Clinic users are billed in tenant plan flow'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if request.user.role != 'INDIVIDUAL':
            return Response(
                {'detail': 'Only individual users can checkout this billing plan'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = BillingCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        success_url = payload.get('success_url') or 'http://localhost:3000/billing/success'
        cancel_url = payload.get('cancel_url') or 'http://localhost:3000/billing/cancel'

        subscription, _ = UserSubscription.objects.get_or_create(user=request.user)

        if not subscription.stripe_subscription_id and subscription.stripe_checkout_session_id:
            try:
                subscription = _sync_subscription_from_checkout_session(subscription)
            except (BillingConfigurationError, BillingProviderError):
                logger.warning(
                    'Failed to sync subscription from checkout session before plan switch',
                    exc_info=True,
                )

        active_or_switchable_statuses = {
            UserSubscription.STATUS_ACTIVE,
            UserSubscription.STATUS_TRIALING,
            UserSubscription.STATUS_PAST_DUE,
            UserSubscription.STATUS_INCOMPLETE,
        }
        if (
            subscription.stripe_subscription_id
            and subscription.status in active_or_switchable_statuses
        ):
            is_plan_change = subscription.plan != payload['plan_id']
            if (
                not is_plan_change
                and subscription.has_active_access()
            ):
                return Response(
                    {
                        'mode': 'already_active',
                        'detail': 'User already has an active subscription on this plan',
                        'plan': subscription.plan,
                    },
                    status=status.HTTP_200_OK,
                )

            if is_plan_change:
                password_error = _validate_plan_change_password(
                    request.user,
                    payload.get('current_password'),
                )
                if password_error:
                    return Response({'detail': password_error}, status=status.HTTP_400_BAD_REQUEST)

            try:
                updated_subscription_payload, price_id = update_subscription_plan(
                    subscription_id=subscription.stripe_subscription_id,
                    plan_id=payload['plan_id'],
                )
                _apply_subscription_payload(
                    subscription=subscription,
                    stripe_subscription_payload=updated_subscription_payload,
                    fallback_plan_id=payload['plan_id'],
                )
                subscription.refresh_from_db()
                if not subscription.stripe_price_id:
                    subscription.stripe_price_id = price_id
                    subscription.save(update_fields=['stripe_price_id', 'updated_at'])
            except (BillingConfigurationError, BillingProviderError) as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            return Response(
                {
                    'mode': 'subscription_updated',
                    'detail': 'Subscription updated successfully',
                    'plan': subscription.plan,
                    'status': subscription.status,
                },
                status=status.HTTP_200_OK,
            )

        try:
            checkout_session, price_id = create_checkout_session(
                user_id=request.user.id,
                user_email=request.user.email,
                plan_id=payload['plan_id'],
                success_url=success_url,
                cancel_url=cancel_url,
            )
        except (BillingConfigurationError, BillingProviderError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        subscription.plan = payload['plan_id']
        subscription.status = UserSubscription.STATUS_INCOMPLETE
        subscription.stripe_checkout_session_id = _payload_get(checkout_session, 'id')
        subscription.stripe_price_id = price_id
        subscription.save()

        return Response(
            {
                'checkout_url': _payload_get(checkout_session, 'url'),
                'checkout_session_id': _payload_get(checkout_session, 'id'),
            },
            status=status.HTTP_200_OK,
        )


class BillingPortalView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not is_stripe_billing_enabled():
            return Response(
                {'detail': 'Stripe billing is disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = BillingPortalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return_url = serializer.validated_data.get('return_url') or 'http://localhost:3000/billing'

        subscription = UserSubscription.objects.filter(user=request.user).first()
        if not subscription:
            return Response(
                {'detail': 'No local subscription found for this user'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not subscription.stripe_customer_id and subscription.stripe_checkout_session_id:
            try:
                subscription = _sync_subscription_from_checkout_session(subscription)
            except (BillingConfigurationError, BillingProviderError) as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not subscription.stripe_customer_id:
            return Response(
                {
                    'detail': (
                        'No Stripe customer found for this user. '
                        'Complete a checkout first or verify webhook delivery.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            portal_session = create_customer_portal_session(
                customer_id=subscription.stripe_customer_id,
                return_url=return_url,
            )
        except (BillingConfigurationError, BillingProviderError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'url': _payload_get(portal_session, 'url')}, status=status.HTTP_200_OK)


class StripeBillingWebhookView(APIView):
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
        except (BillingConfigurationError, BillingProviderError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            _process_stripe_event(event_payload)
        except Exception:
            logger.error('Failed to process Stripe webhook event', exc_info=True)
            return Response({'detail': 'Webhook processing failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'status': 'ok'}, status=status.HTTP_200_OK)
