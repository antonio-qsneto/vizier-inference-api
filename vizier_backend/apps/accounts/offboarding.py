"""
Offboarding governance service for account cancellation/deletion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.tenants.models import Clinic, DoctorInvitation, Membership

from .billing import (
    BillingConfigurationError,
    BillingProviderError,
    retrieve_subscription as retrieve_individual_subscription,
    timestamp_to_datetime as individual_timestamp_to_datetime,
)
from .models import User, UserSubscription
from .rbac import RBACRole, resolve_effective_role
from apps.tenants.billing import (
    ClinicBillingConfigurationError,
    ClinicBillingProviderError,
    retrieve_subscription as retrieve_clinic_subscription,
    timestamp_to_datetime as clinic_timestamp_to_datetime,
)


@dataclass(frozen=True)
class OffboardingBlocker:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {'code': self.code, 'message': self.message}


@dataclass(frozen=True)
class OffboardingStatus:
    effective_role: str | None
    can_cancel_subscription: bool
    can_delete_account: bool
    blockers: list[OffboardingBlocker]
    subscription_scope: str
    status: str | None
    billing_period_end: datetime | None

    def as_dict(self) -> dict:
        return {
            'effective_role': self.effective_role,
            'can_cancel_subscription': self.can_cancel_subscription,
            'can_delete_account': self.can_delete_account,
            'blockers': [item.as_dict() for item in self.blockers],
            'subscription_scope': self.subscription_scope,
            'status': self.status,
            'billing_period_end': self.billing_period_end,
        }


def _obj_get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _stripe_entitlement_active(*, stripe_status: str | None, period_end: datetime | None) -> bool:
    normalized = str(stripe_status or '').strip().lower()
    now = timezone.now()
    if normalized in {'active', 'trialing', 'past_due', 'unpaid', 'incomplete', 'incomplete_expired'}:
        if period_end:
            return period_end > now
        return True
    if normalized in {'canceled', 'cancelled'}:
        return bool(period_end and period_end > now)
    return False


def _clinic_team_blockers(clinic: Clinic) -> list[OffboardingBlocker]:
    blockers: list[OffboardingBlocker] = []
    if clinic.get_active_doctors_count() > 0:
        blockers.append(
            OffboardingBlocker(
                code='CLINIC_DOCTORS_REMAIN',
                message='Remova todos os doctors da clínica antes de cancelar/excluir a conta.',
            )
        )

    if DoctorInvitation.objects.filter(clinic=clinic, status='PENDING').exists():
        blockers.append(
            OffboardingBlocker(
                code='CLINIC_PENDING_INVITATIONS',
                message='Cancele todos os convites pendentes antes de cancelar/excluir a conta.',
            )
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
            OffboardingBlocker(
                code='CLINIC_CO_ADMINS_REMAIN',
                message='Remova todos os co-admins antes de cancelar/excluir a conta.',
            )
        )
    return blockers


def _individual_subscription_ended(subscription: UserSubscription) -> bool:
    if subscription.status != UserSubscription.STATUS_CANCELED:
        return False
    if not subscription.current_period_end:
        return True
    return subscription.current_period_end <= timezone.now()


def _clinic_subscription_ended(clinic: Clinic) -> bool:
    if clinic.account_status != Clinic.ACCOUNT_STATUS_CANCELED:
        return False
    if clinic.stripe_current_period_end:
        return clinic.stripe_current_period_end <= timezone.now()
    return bool(clinic.canceled_at and not clinic.stripe_subscription_id and not clinic.cancel_at_period_end)


def build_offboarding_status(user: User) -> OffboardingStatus:
    effective_role = resolve_effective_role(user)
    blockers: list[OffboardingBlocker] = []
    subscription_scope = 'none'
    status_value = None
    billing_period_end = None
    can_cancel_subscription = False

    if user.is_deleted():
        blockers.append(
            OffboardingBlocker(
                code='ACCOUNT_ALREADY_DELETED',
                message='Conta já está excluída.',
            )
        )

    if effective_role == RBACRole.CLINIC_DOCTOR and user.clinic_id:
        subscription_scope = 'clinic'
        status_value = user.clinic.account_status if user.clinic else None
        billing_period_end = user.clinic.stripe_current_period_end if user.clinic else None
        blockers.append(
            OffboardingBlocker(
                code='DOCTOR_MUST_LEAVE_CLINIC',
                message='Doctors vinculados devem se desvincular da clínica antes de excluir a conta.',
            )
        )

    if effective_role == RBACRole.CLINIC_ADMIN and user.clinic:
        clinic = user.clinic
        subscription_scope = 'clinic'
        status_value = clinic.account_status
        billing_period_end = clinic.stripe_current_period_end

        team_blockers = _clinic_team_blockers(clinic)
        if clinic.stripe_subscription_id and not _clinic_subscription_ended(clinic) and not team_blockers:
            can_cancel_subscription = True

        blockers.extend(team_blockers)

        if clinic.stripe_subscription_id:
            try:
                stripe_payload = retrieve_clinic_subscription(clinic.stripe_subscription_id)
            except (ClinicBillingConfigurationError, ClinicBillingProviderError):
                blockers.append(
                    OffboardingBlocker(
                        code='CLINIC_STRIPE_VERIFICATION_UNAVAILABLE',
                        message='Não foi possível validar a assinatura da clínica no Stripe. Tente novamente.',
                    )
                )
            else:
                stripe_status = _obj_get(stripe_payload, 'status')
                stripe_period_end = clinic_timestamp_to_datetime(
                    _obj_get(stripe_payload, 'current_period_end')
                )
                if stripe_period_end:
                    billing_period_end = stripe_period_end
                if _stripe_entitlement_active(
                    stripe_status=stripe_status,
                    period_end=stripe_period_end,
                ):
                    blockers.append(
                        OffboardingBlocker(
                            code='CLINIC_SUBSCRIPTION_ACTIVE',
                            message='A assinatura da clínica ainda está ativa. Cancele e aguarde o fim do ciclo.',
                        )
                    )
        else:
            if clinic.can_use_clinic_resources() or clinic.account_status != Clinic.ACCOUNT_STATUS_CANCELED:
                blockers.append(
                    OffboardingBlocker(
                        code='CLINIC_SUBSCRIPTION_NOT_ENDED',
                        message='A assinatura da clínica ainda não foi encerrada.',
                    )
                )

    if effective_role == RBACRole.INDIVIDUAL or (
        effective_role != RBACRole.CLINIC_ADMIN and not user.clinic_id
    ):
        subscription = UserSubscription.objects.filter(user=user).first()
        if subscription:
            subscription_scope = 'individual'
            status_value = subscription.status.lower()
            billing_period_end = subscription.current_period_end
            if subscription.stripe_subscription_id and not _individual_subscription_ended(subscription):
                can_cancel_subscription = True

            if subscription.stripe_subscription_id:
                try:
                    stripe_payload = retrieve_individual_subscription(subscription.stripe_subscription_id)
                except (BillingConfigurationError, BillingProviderError):
                    blockers.append(
                        OffboardingBlocker(
                            code='INDIVIDUAL_STRIPE_VERIFICATION_UNAVAILABLE',
                            message='Não foi possível validar a assinatura individual no Stripe. Tente novamente.',
                        )
                    )
                else:
                    stripe_status = _obj_get(stripe_payload, 'status')
                    stripe_period_end = individual_timestamp_to_datetime(
                        _obj_get(stripe_payload, 'current_period_end')
                    )
                    if stripe_period_end:
                        billing_period_end = stripe_period_end
                    if _stripe_entitlement_active(
                        stripe_status=stripe_status,
                        period_end=stripe_period_end,
                    ):
                        blockers.append(
                            OffboardingBlocker(
                                code='INDIVIDUAL_SUBSCRIPTION_ACTIVE',
                                message='A assinatura individual ainda está ativa. Cancele e aguarde o fim do ciclo.',
                            )
                        )
            elif subscription.has_active_access():
                blockers.append(
                    OffboardingBlocker(
                        code='INDIVIDUAL_SUBSCRIPTION_ACTIVE_LOCAL',
                        message='A assinatura individual ainda está ativa localmente.',
                    )
                )

    can_delete_account = len(blockers) == 0
    return OffboardingStatus(
        effective_role=effective_role,
        can_cancel_subscription=bool(can_cancel_subscription),
        can_delete_account=can_delete_account,
        blockers=blockers,
        subscription_scope=subscription_scope,
        status=status_value,
        billing_period_end=billing_period_end,
    )


def soft_delete_user_account(user: User) -> None:
    if user.is_deleted():
        return

    deleted_email = f'deleted+{user.id}@deleted.local'
    timestamp = timezone.now()

    with transaction.atomic():
        user.email = deleted_email
        user.first_name = ''
        user.last_name = ''
        user.is_active = False
        user.account_lifecycle_status = User.ACCOUNT_LIFECYCLE_DELETED
        user.deleted_at = timestamp
        user.anonymized_at = timestamp
        user.set_unusable_password()
        user.save(
            update_fields=[
                'email',
                'first_name',
                'last_name',
                'password',
                'is_active',
                'account_lifecycle_status',
                'deleted_at',
                'anonymized_at',
                'updated_at',
            ]
        )
