"""
Stripe billing helpers for clinic/account subscriptions with seat-based pricing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
import hashlib
import logging
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .billing_ledger import (
    mark_event_applied,
    register_clinic_event,
    stripe_event_created_at,
)
from .models import Clinic, Membership, StripeWebhookEvent

logger = logging.getLogger(__name__)


class ClinicBillingConfigurationError(Exception):
    """Raised when clinic billing configuration is invalid."""


class ClinicBillingProviderError(Exception):
    """Raised when Stripe provider operations fail."""


@dataclass(frozen=True)
class ClinicBillingPlanDefinition:
    id: str
    label: str
    price_label: str
    summary: str
    interval: str
    currency: str
    amount_cents: int
    lookup_key: str


PLAN_DEFINITIONS = {
    Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY: ClinicBillingPlanDefinition(
        id=Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
        label='Plano clinica mensal',
        price_label='R$ 679,00/medico/mes',
        summary='Cobranca mensal por medico (assento licenciado).',
        interval='month',
        currency='brl',
        amount_cents=67900,
        lookup_key='price_clinic_monthly',
    ),
    Clinic.SUBSCRIPTION_PLAN_CLINIC_YEARLY: ClinicBillingPlanDefinition(
        id=Clinic.SUBSCRIPTION_PLAN_CLINIC_YEARLY,
        label='Plano clinica anual',
        price_label='R$ 7.333,00/medico/ano',
        summary='Cobranca anual por medico com 10% de desconto.',
        interval='year',
        currency='brl',
        amount_cents=733300,
        lookup_key='price_clinic_yearly',
    ),
}


def _obj_get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _obj_to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    to_recursive = getattr(obj, 'to_dict_recursive', None)
    if callable(to_recursive):
        return to_recursive()
    to_dict = getattr(obj, 'to_dict', None)
    if callable(to_dict):
        return to_dict()
    return {}


def is_stripe_billing_enabled() -> bool:
    return bool(getattr(settings, 'ENABLE_STRIPE_BILLING', False))


def _get_stripe_sdk():
    try:
        import stripe
    except ImportError as exc:
        raise ClinicBillingConfigurationError('stripe package is not installed') from exc
    return stripe


def _get_stripe_secret_key() -> str:
    key = (
        getattr(settings, 'STRIPE_SECRET_KEY', None)
        or getattr(settings, 'STRIPE_API_KEY', None)
    )
    if not key:
        raise ClinicBillingConfigurationError('Missing Stripe secret key')
    return key


def _price_id_for_plan(plan_id: str) -> str:
    if plan_id == Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY:
        value = getattr(settings, 'STRIPE_PRICE_ID_CLINIC_MONTHLY', None)
    elif plan_id == Clinic.SUBSCRIPTION_PLAN_CLINIC_YEARLY:
        value = getattr(settings, 'STRIPE_PRICE_ID_CLINIC_YEARLY', None)
    else:
        value = None

    if not value:
        raise ClinicBillingConfigurationError(f'Missing Stripe price id for plan {plan_id}')

    return str(value)


def get_plan_definition(plan_id: str) -> ClinicBillingPlanDefinition:
    if plan_id not in PLAN_DEFINITIONS:
        raise ClinicBillingConfigurationError(f'Unsupported clinic plan_id: {plan_id}')
    return PLAN_DEFINITIONS[plan_id]


def list_clinic_billing_plans() -> list[dict[str, Any]]:
    plans = []
    for definition in PLAN_DEFINITIONS.values():
        plans.append(
            {
                'id': definition.id,
                'label': definition.label,
                'price_label': definition.price_label,
                'summary': definition.summary,
                'interval': definition.interval,
                'lookup_key': definition.lookup_key,
                'discount': '10% off' if definition.id == Clinic.SUBSCRIPTION_PLAN_CLINIC_YEARLY else None,
            }
        )
    return plans


def timestamp_to_datetime(value: Any):
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def normalize_account_status(stripe_status: str | None) -> str:
    normalized = (stripe_status or '').strip().lower()
    if normalized in {'active', 'trialing'}:
        return Clinic.ACCOUNT_STATUS_ACTIVE
    if normalized in {'past_due', 'unpaid', 'incomplete', 'incomplete_expired'}:
        return Clinic.ACCOUNT_STATUS_PAST_DUE
    return Clinic.ACCOUNT_STATUS_CANCELED


def configured_dunning_grace_days() -> int:
    raw = getattr(settings, 'BILLING_DUNNING_GRACE_DAYS', 7)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 7


def compute_grace_until(reference_dt: datetime | None = None) -> datetime:
    reference_dt = reference_dt or timezone.now()
    return reference_dt + timedelta(days=configured_dunning_grace_days())


def apply_clinic_dunning_policy(
    *,
    clinic: Clinic,
    target_status: str,
    reference_dt: datetime | None = None,
) -> None:
    if target_status == Clinic.ACCOUNT_STATUS_ACTIVE:
        clinic.billing_grace_until = None
        return

    if target_status == Clinic.ACCOUNT_STATUS_PAST_DUE:
        computed = compute_grace_until(reference_dt)
        if clinic.billing_grace_until and clinic.billing_grace_until > computed:
            return
        clinic.billing_grace_until = computed
        return

    clinic.billing_grace_until = None


def infer_plan_id_from_price_id(price_id: str | None) -> str | None:
    if not price_id:
        return None

    monthly = getattr(settings, 'STRIPE_PRICE_ID_CLINIC_MONTHLY', None)
    yearly = getattr(settings, 'STRIPE_PRICE_ID_CLINIC_YEARLY', None)

    if monthly and price_id == monthly:
        return Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY
    if yearly and price_id == yearly:
        return Clinic.SUBSCRIPTION_PLAN_CLINIC_YEARLY

    try:
        stripe = _get_stripe_sdk()
        stripe.api_key = _get_stripe_secret_key()
        price = stripe.Price.retrieve(price_id)
    except Exception:
        return None

    recurring = _obj_get(price, 'recurring', {}) or {}
    interval = _obj_get(recurring, 'interval')
    if interval == 'month':
        return Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY
    if interval == 'year':
        return Clinic.SUBSCRIPTION_PLAN_CLINIC_YEARLY
    return None


def resolve_checkout_quantity(
    *,
    clinic: Clinic,
    requested_quantity: int | None = None,
) -> int:
    seat_usage = count_doctor_seats(clinic)

    if requested_quantity is not None:
        try:
            quantity = int(requested_quantity)
        except (TypeError, ValueError) as exc:
            raise ClinicBillingConfigurationError('Invalid checkout seat quantity') from exc

        if quantity < 1:
            raise ClinicBillingConfigurationError('Checkout seat quantity must be at least 1')
        if quantity < seat_usage:
            raise ClinicBillingConfigurationError(
                f'Checkout seat quantity ({quantity}) cannot be lower than active doctors ({seat_usage})'
            )
        return quantity

    if seat_usage < 1:
        raise ClinicBillingConfigurationError(
            'At least one doctor membership is required to start clinic billing'
        )
    return seat_usage


def count_doctor_seats(clinic: Clinic) -> int:
    return clinic.get_active_doctors_count()


def ensure_owner_membership(clinic: Clinic) -> None:
    Membership.objects.get_or_create(
        account=clinic,
        user=clinic.owner,
        defaults={'role': Membership.ROLE_ADMIN},
    )


def _extract_first_item(subscription_payload: Any) -> dict[str, Any] | None:
    items = _obj_get(_obj_get(subscription_payload, 'items', {}) or {}, 'data', []) or []
    if not items:
        return None
    return _obj_to_dict(items[0])


def extract_subscription_item_id(subscription_payload: Any) -> str | None:
    first_item = _extract_first_item(subscription_payload)
    if not first_item:
        return None
    value = _obj_get(first_item, 'id')
    return str(value) if value else None


def extract_subscription_price_id(subscription_payload: Any) -> str | None:
    first_item = _extract_first_item(subscription_payload)
    if not first_item:
        return None
    price = _obj_get(first_item, 'price', {}) or {}
    value = _obj_get(price, 'id')
    return str(value) if value else None


def extract_subscription_quantity(subscription_payload: Any) -> int | None:
    first_item = _extract_first_item(subscription_payload)
    if not first_item:
        return None
    value = _obj_get(first_item, 'quantity')
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def subscription_state_fingerprint(subscription_payload: Any) -> str:
    payload_dict = _obj_to_dict(subscription_payload)
    signature = '|'.join(
        [
            str(_obj_get(payload_dict, 'id') or ''),
            str(_obj_get(payload_dict, 'status') or ''),
            str(_obj_get(payload_dict, 'current_period_end') or ''),
            str(extract_subscription_price_id(payload_dict) or ''),
            str(extract_subscription_quantity(payload_dict) or ''),
        ]
    )
    return hashlib.sha256(signature.encode('utf-8')).hexdigest()[:24]


def retrieve_subscription(subscription_id: str):
    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()
    try:
        return stripe.Subscription.retrieve(subscription_id)
    except Exception as exc:
        raise ClinicBillingProviderError(f'Failed to retrieve Stripe subscription: {exc}') from exc


def retrieve_checkout_session(checkout_session_id: str):
    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()
    try:
        return stripe.checkout.Session.retrieve(checkout_session_id)
    except Exception as exc:
        raise ClinicBillingProviderError(f'Failed to retrieve Stripe checkout session: {exc}') from exc


def create_checkout_session(
    *,
    clinic: Clinic,
    initiated_by_user_id: int,
    plan_id: str,
    success_url: str,
    cancel_url: str,
    requested_quantity: int | None = None,
):
    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()

    price_id = _price_id_for_plan(plan_id)
    quantity = resolve_checkout_quantity(
        clinic=clinic,
        requested_quantity=requested_quantity,
    )

    payload = {
        'line_items': [{'price': price_id, 'quantity': quantity}],
        'mode': 'subscription',
        'success_url': success_url,
        'cancel_url': cancel_url,
        'client_reference_id': str(clinic.id),
        'metadata': {
            'clinic_id': str(clinic.id),
            'initiated_by_user_id': str(initiated_by_user_id),
            'plan_id': plan_id,
            'quantity': str(quantity),
        },
        'subscription_data': {
            'metadata': {
                'clinic_id': str(clinic.id),
                'plan_id': plan_id,
            }
        },
        'allow_promotion_codes': True,
    }

    if clinic.stripe_customer_id:
        payload['customer'] = clinic.stripe_customer_id
    else:
        payload['customer_email'] = clinic.owner.email

    try:
        checkout_session = stripe.checkout.Session.create(**payload)
    except Exception as exc:
        raise ClinicBillingProviderError(
            f'Failed to create clinic Stripe checkout session: {exc}'
        ) from exc

    return checkout_session, price_id, quantity


def _resolve_subscription_item_id(clinic: Clinic, subscription_payload: Any) -> str:
    item_id = clinic.stripe_subscription_item_id or extract_subscription_item_id(subscription_payload)
    if not item_id:
        raise ClinicBillingProviderError('Stripe subscription item id is missing')
    return item_id


def update_subscription_price(
    *,
    clinic: Clinic,
    plan_id: str,
    quantity: int,
    proration_behavior: str = 'create_prorations',
):
    if quantity < 1:
        raise ClinicBillingConfigurationError('Seat quantity must be at least 1')
    if not clinic.stripe_subscription_id:
        raise ClinicBillingConfigurationError('Clinic has no Stripe subscription id')

    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()

    price_id = _price_id_for_plan(plan_id)

    try:
        current_subscription = stripe.Subscription.retrieve(clinic.stripe_subscription_id)
    except Exception as exc:
        raise ClinicBillingProviderError(
            f'Failed to retrieve Stripe subscription for plan change: {exc}'
        ) from exc

    subscription_item_id = _resolve_subscription_item_id(clinic, current_subscription)

    try:
        updated_subscription = stripe.Subscription.modify(
            clinic.stripe_subscription_id,
            cancel_at_period_end=False,
            proration_behavior=proration_behavior,
            items=[
                {
                    'id': subscription_item_id,
                    'price': price_id,
                    'quantity': quantity,
                }
            ],
            metadata={
                'clinic_id': str(clinic.id),
                'plan_id': plan_id,
                'quantity': str(quantity),
            },
        )
    except Exception as exc:
        raise ClinicBillingProviderError(f'Failed to update clinic plan: {exc}') from exc

    return updated_subscription, price_id


def update_subscription_quantity(
    *,
    clinic: Clinic,
    quantity: int,
    proration_behavior: str = 'create_prorations',
):
    if quantity < 1:
        raise ClinicBillingConfigurationError('Seat quantity must be at least 1')
    if not clinic.stripe_subscription_id:
        raise ClinicBillingConfigurationError('Clinic has no Stripe subscription id')

    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()

    try:
        current_subscription = stripe.Subscription.retrieve(clinic.stripe_subscription_id)
    except Exception as exc:
        raise ClinicBillingProviderError(
            f'Failed to retrieve Stripe subscription for seat update: {exc}'
        ) from exc

    subscription_item_id = _resolve_subscription_item_id(clinic, current_subscription)
    current_price_id = extract_subscription_price_id(current_subscription)

    item_payload = {
        'id': subscription_item_id,
        'quantity': quantity,
    }
    if current_price_id:
        item_payload['price'] = current_price_id

    try:
        updated_subscription = stripe.Subscription.modify(
            clinic.stripe_subscription_id,
            cancel_at_period_end=False,
            proration_behavior=proration_behavior,
            items=[item_payload],
            metadata={
                'clinic_id': str(clinic.id),
                'quantity': str(quantity),
            },
        )
    except Exception as exc:
        raise ClinicBillingProviderError(f'Failed to update seat quantity: {exc}') from exc

    return updated_subscription


def schedule_downgrade_to_individual(*, clinic: Clinic):
    if not clinic.stripe_subscription_id:
        raise ClinicBillingConfigurationError('Clinic has no Stripe subscription id')

    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()

    metadata = {
        'clinic_id': str(clinic.id),
        'pending_downgrade_to_individual': '1',
    }

    try:
        return stripe.Subscription.modify(
            clinic.stripe_subscription_id,
            cancel_at_period_end=True,
            proration_behavior='none',
            metadata=metadata,
        )
    except Exception as exc:
        raise ClinicBillingProviderError(
            f'Failed to schedule clinic downgrade to individual: {exc}'
        ) from exc


def cancel_clinic_subscription_at_period_end(*, clinic: Clinic):
    if not clinic.stripe_subscription_id:
        raise ClinicBillingConfigurationError('Clinic has no Stripe subscription id')

    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()

    metadata = {
        'clinic_id': str(clinic.id),
        'canceled_by': 'api',
    }

    try:
        return stripe.Subscription.modify(
            clinic.stripe_subscription_id,
            cancel_at_period_end=True,
            proration_behavior='none',
            metadata=metadata,
        )
    except Exception as exc:
        raise ClinicBillingProviderError(
            f'Failed to cancel clinic subscription at period end: {exc}'
        ) from exc


def create_customer_portal_session(*, customer_id: str, return_url: str):
    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()

    try:
        return stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
    except Exception as exc:
        raise ClinicBillingProviderError(
            f'Failed to create Stripe billing portal session: {exc}'
        ) from exc


def construct_webhook_event(*, payload: bytes, signature: str):
    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)
    if not webhook_secret:
        raise ClinicBillingConfigurationError('Missing STRIPE_WEBHOOK_SECRET')

    try:
        return stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=webhook_secret,
        )
    except Exception as exc:
        raise ClinicBillingProviderError(
            f'Invalid Stripe webhook signature/payload: {exc}'
        ) from exc


def apply_subscription_payload(
    *,
    clinic: Clinic,
    stripe_subscription_payload: Any,
    fallback_plan_id: str | None = None,
    event_created_at: datetime | None = None,
) -> Clinic:
    subscription_payload = _obj_to_dict(stripe_subscription_payload)

    stripe_subscription_id = _obj_get(subscription_payload, 'id')
    stripe_customer_id = _obj_get(subscription_payload, 'customer')
    stripe_status = _obj_get(subscription_payload, 'status')
    cancel_at_period_end = bool(_obj_get(subscription_payload, 'cancel_at_period_end', False))
    price_id = extract_subscription_price_id(subscription_payload)
    quantity = extract_subscription_quantity(subscription_payload)
    item_id = extract_subscription_item_id(subscription_payload)

    inferred_plan = infer_plan_id_from_price_id(price_id)
    plan_id = inferred_plan or fallback_plan_id or clinic.subscription_plan
    if plan_id not in PLAN_DEFINITIONS:
        plan_id = Clinic.SUBSCRIPTION_PLAN_FREE

    clinic.plan_type = Clinic.PLAN_TYPE_CLINIC
    clinic.subscription_plan = plan_id
    normalized_status = normalize_account_status(stripe_status)
    if cancel_at_period_end and normalized_status in {
        Clinic.ACCOUNT_STATUS_ACTIVE,
        Clinic.ACCOUNT_STATUS_PAST_DUE,
    }:
        normalized_status = Clinic.ACCOUNT_STATUS_CANCELED
    clinic.account_status = normalized_status
    apply_clinic_dunning_policy(
        clinic=clinic,
        target_status=clinic.account_status,
        reference_dt=event_created_at,
    )
    if stripe_subscription_id:
        clinic.stripe_subscription_id = str(stripe_subscription_id)
    if stripe_customer_id:
        clinic.stripe_customer_id = str(stripe_customer_id)
    if item_id:
        clinic.stripe_subscription_item_id = str(item_id)
    if price_id:
        clinic.stripe_price_id = str(price_id)
    if quantity is not None:
        clinic.seat_limit = int(quantity)

    current_period_end = timestamp_to_datetime(_obj_get(subscription_payload, 'current_period_end'))
    clinic.stripe_current_period_end = current_period_end
    clinic.cancel_at_period_end = cancel_at_period_end
    if clinic.account_status == Clinic.ACCOUNT_STATUS_CANCELED:
        if not clinic.canceled_at:
            clinic.canceled_at = event_created_at or timezone.now()
    elif not cancel_at_period_end:
        clinic.canceled_at = None

    clinic.save(
        update_fields=[
            'plan_type',
            'subscription_plan',
            'account_status',
            'cancel_at_period_end',
            'canceled_at',
            'stripe_subscription_id',
            'stripe_customer_id',
            'stripe_subscription_item_id',
            'stripe_price_id',
            'seat_limit',
            'stripe_current_period_end',
            'billing_grace_until',
            'updated_at',
        ]
    )
    return clinic


def schedule_seat_reduction(*, clinic: Clinic, target_quantity: int) -> Clinic:
    if target_quantity < 1:
        raise ClinicBillingConfigurationError('Seat quantity must be at least 1')

    effective_at = clinic.stripe_current_period_end or timezone.now()
    clinic.scheduled_seat_limit = target_quantity
    clinic.scheduled_seat_effective_at = effective_at
    clinic.save(update_fields=['scheduled_seat_limit', 'scheduled_seat_effective_at', 'updated_at'])
    return clinic


def clear_scheduled_seat_reduction(*, clinic: Clinic) -> Clinic:
    if clinic.scheduled_seat_limit is None and clinic.scheduled_seat_effective_at is None:
        return clinic
    clinic.scheduled_seat_limit = None
    clinic.scheduled_seat_effective_at = None
    clinic.save(update_fields=['scheduled_seat_limit', 'scheduled_seat_effective_at', 'updated_at'])
    return clinic


def apply_scheduled_seat_reduction_if_due(*, clinic: Clinic) -> bool:
    if clinic.scheduled_seat_limit is None:
        return False

    if not clinic.stripe_subscription_id:
        clear_scheduled_seat_reduction(clinic=clinic)
        return False

    effective_at = clinic.scheduled_seat_effective_at
    if effective_at and timezone.now() < effective_at:
        return False

    updated_subscription_payload = update_subscription_quantity(
        clinic=clinic,
        quantity=clinic.scheduled_seat_limit,
        proration_behavior='none',
    )
    apply_subscription_payload(clinic=clinic, stripe_subscription_payload=updated_subscription_payload)
    clear_scheduled_seat_reduction(clinic=clinic)
    return True


def sync_seat_quantity_with_stripe(
    *,
    clinic: Clinic,
    allow_yearly_decrease_now: bool = False,
) -> Clinic:
    if not clinic.stripe_subscription_id:
        return clinic

    desired_quantity = count_doctor_seats(clinic)
    if desired_quantity < 1:
        raise ClinicBillingConfigurationError(
            'Clinic subscription requires at least one active doctor seat'
        )

    current_quantity = int(clinic.seat_limit or 0)
    if desired_quantity == current_quantity:
        return clinic

    if desired_quantity < current_quantity and not allow_yearly_decrease_now:
        return schedule_seat_reduction(clinic=clinic, target_quantity=desired_quantity)

    updated_subscription_payload = update_subscription_quantity(
        clinic=clinic,
        quantity=desired_quantity,
        proration_behavior='create_prorations',
    )
    apply_subscription_payload(clinic=clinic, stripe_subscription_payload=updated_subscription_payload)

    if desired_quantity >= current_quantity:
        clear_scheduled_seat_reduction(clinic=clinic)

    return clinic


def _resolve_clinic_for_event(payload: Any) -> Clinic | None:
    payload_dict = _obj_to_dict(payload)

    metadata = _obj_get(payload_dict, 'metadata', {}) or {}
    clinic_id = metadata.get('clinic_id') or _obj_get(payload_dict, 'client_reference_id')
    stripe_subscription_id = _obj_get(payload_dict, 'subscription') or _obj_get(payload_dict, 'id')
    stripe_customer_id = _obj_get(payload_dict, 'customer')

    clinic = None
    if clinic_id:
        clinic = Clinic.objects.filter(id=clinic_id).first()
        if clinic:
            return clinic

    if stripe_subscription_id:
        clinic = Clinic.objects.filter(stripe_subscription_id=stripe_subscription_id).first()
        if clinic:
            return clinic

    if stripe_customer_id:
        clinic = Clinic.objects.filter(stripe_customer_id=stripe_customer_id).first()
        if clinic:
            return clinic

    return None


def _process_checkout_session_completed(event_payload: dict[str, Any]) -> None:
    checkout_payload = _obj_get(_obj_get(event_payload, 'data', {}) or {}, 'object', {}) or {}
    clinic = _resolve_clinic_for_event(checkout_payload)
    if not clinic:
        return
    event_created_at = stripe_event_created_at(event_payload)

    stripe_customer_id = _obj_get(checkout_payload, 'customer')
    stripe_subscription_id = _obj_get(checkout_payload, 'subscription')
    metadata = _obj_get(checkout_payload, 'metadata', {}) or {}
    fallback_plan_id = metadata.get('plan_id') or clinic.subscription_plan

    fields_to_update = []
    if stripe_customer_id and stripe_customer_id != clinic.stripe_customer_id:
        clinic.stripe_customer_id = stripe_customer_id
        fields_to_update.append('stripe_customer_id')
    if stripe_subscription_id and stripe_subscription_id != clinic.stripe_subscription_id:
        clinic.stripe_subscription_id = stripe_subscription_id
        fields_to_update.append('stripe_subscription_id')

    if fields_to_update:
        clinic.save(update_fields=fields_to_update + ['updated_at'])

    if stripe_subscription_id:
        stripe_subscription_payload = retrieve_subscription(stripe_subscription_id)
        apply_subscription_payload(
            clinic=clinic,
            stripe_subscription_payload=stripe_subscription_payload,
            fallback_plan_id=fallback_plan_id,
            event_created_at=event_created_at,
        )


def _process_subscription_updated(event_payload: dict[str, Any]) -> None:
    stripe_subscription_payload = _obj_get(_obj_get(event_payload, 'data', {}) or {}, 'object', {}) or {}
    clinic = _resolve_clinic_for_event(stripe_subscription_payload)
    if not clinic:
        return

    apply_subscription_payload(
        clinic=clinic,
        stripe_subscription_payload=stripe_subscription_payload,
        event_created_at=stripe_event_created_at(event_payload),
    )


def _process_subscription_deleted(event_payload: dict[str, Any]) -> None:
    stripe_subscription_payload = _obj_get(_obj_get(event_payload, 'data', {}) or {}, 'object', {}) or {}
    clinic = _resolve_clinic_for_event(stripe_subscription_payload)
    if not clinic:
        return

    clinic.subscription_plan = Clinic.SUBSCRIPTION_PLAN_FREE
    clinic.stripe_customer_id = None
    clinic.stripe_subscription_id = None
    clinic.stripe_subscription_item_id = None
    clinic.stripe_price_id = None
    clinic.cancel_at_period_end = False
    clinic.plan_type = Clinic.PLAN_TYPE_CLINIC
    clinic.account_status = Clinic.ACCOUNT_STATUS_CANCELED
    clinic.seat_limit = 0
    if not clinic.canceled_at:
        clinic.canceled_at = stripe_event_created_at(event_payload)

    clinic.scheduled_seat_limit = None
    clinic.scheduled_seat_effective_at = None
    clinic.stripe_current_period_end = timestamp_to_datetime(
        _obj_get(stripe_subscription_payload, 'current_period_end')
    )
    clinic.billing_grace_until = None
    clinic.save(
        update_fields=[
            'plan_type',
            'account_status',
            'subscription_plan',
            'cancel_at_period_end',
            'canceled_at',
            'stripe_customer_id',
            'stripe_subscription_id',
            'stripe_subscription_item_id',
            'stripe_price_id',
            'seat_limit',
            'scheduled_seat_limit',
            'scheduled_seat_effective_at',
            'stripe_current_period_end',
            'billing_grace_until',
            'updated_at',
        ]
    )


def _process_invoice_paid(event_payload: dict[str, Any]) -> None:
    invoice_payload = _obj_get(_obj_get(event_payload, 'data', {}) or {}, 'object', {}) or {}
    clinic = _resolve_clinic_for_event(invoice_payload)
    if not clinic:
        return

    clinic.account_status = Clinic.ACCOUNT_STATUS_ACTIVE
    apply_clinic_dunning_policy(
        clinic=clinic,
        target_status=clinic.account_status,
        reference_dt=stripe_event_created_at(event_payload),
    )
    clinic.save(update_fields=['account_status', 'billing_grace_until', 'updated_at'])

    stripe_subscription_id = _obj_get(invoice_payload, 'subscription')
    if stripe_subscription_id:
        stripe_subscription_payload = retrieve_subscription(stripe_subscription_id)
        apply_subscription_payload(
            clinic=clinic,
            stripe_subscription_payload=stripe_subscription_payload,
            event_created_at=stripe_event_created_at(event_payload),
        )

    apply_scheduled_seat_reduction_if_due(clinic=clinic)


def _process_invoice_payment_failed(event_payload: dict[str, Any]) -> None:
    invoice_payload = _obj_get(_obj_get(event_payload, 'data', {}) or {}, 'object', {}) or {}
    clinic = _resolve_clinic_for_event(invoice_payload)
    if not clinic:
        return

    clinic.account_status = Clinic.ACCOUNT_STATUS_PAST_DUE
    apply_clinic_dunning_policy(
        clinic=clinic,
        target_status=clinic.account_status,
        reference_dt=stripe_event_created_at(event_payload),
    )
    clinic.save(update_fields=['account_status', 'billing_grace_until', 'updated_at'])


def process_stripe_event(event_payload: Any) -> None:
    payload_dict = _obj_to_dict(event_payload)
    event_type = _obj_get(payload_dict, 'type')

    if event_type == 'checkout.session.completed':
        _process_checkout_session_completed(payload_dict)
        return

    if event_type == 'invoice.paid':
        _process_invoice_paid(payload_dict)
        return

    if event_type == 'invoice.payment_failed':
        _process_invoice_payment_failed(payload_dict)
        return

    if event_type == 'customer.subscription.updated':
        _process_subscription_updated(payload_dict)
        return

    if event_type == 'customer.subscription.deleted':
        _process_subscription_deleted(payload_dict)
        return


def reconcile_clinic_subscription_state(*, clinic: Clinic) -> bool:
    if not clinic.stripe_subscription_id:
        return False

    stripe_subscription_payload = retrieve_subscription(clinic.stripe_subscription_id)
    stripe_subscription_payload_dict = _obj_to_dict(stripe_subscription_payload)
    stripe_subscription_id = _obj_get(stripe_subscription_payload_dict, 'id') or clinic.stripe_subscription_id
    event_created_at = timezone.now()
    idempotency_key = (
        f"reconcile:clinic:{clinic.id}:"
        f"{subscription_state_fingerprint(stripe_subscription_payload_dict)}"
    )
    registration = register_clinic_event(
        clinic=clinic,
        source='reconciliation',
        event_type='subscription.snapshot',
        event_created_at=event_created_at,
        idempotency_key=idempotency_key,
        stripe_event_id=None,
        stripe_subscription_id=str(stripe_subscription_id or ''),
        payload=stripe_subscription_payload_dict,
    )
    if not registration.should_apply:
        return False

    ledger_entry = registration.entry
    try:
        apply_subscription_payload(
            clinic=clinic,
            stripe_subscription_payload=stripe_subscription_payload_dict,
            fallback_plan_id=clinic.subscription_plan,
            event_created_at=event_created_at,
        )
        mark_event_applied(ledger_entry)
        return True
    except Exception:
        if ledger_entry:
            ledger_entry.delete()
        raise


def _audit_webhook_event(
    *,
    payload_dict: dict[str, Any],
    event_id: str,
    event_type: str,
    outcome: str,
    reason: str | None = None,
) -> None:
    object_payload = _obj_get(_obj_get(payload_dict, 'data', {}) or {}, 'object', {}) or {}
    clinic = _resolve_clinic_for_event(object_payload)
    if not clinic:
        return

    from apps.audit.services import AuditService

    try:
        AuditService.log_billing_webhook_outcome(
            clinic=clinic,
            event_id=event_id,
            event_type=event_type,
            outcome=outcome,
            reason=reason,
            user=None,
            livemode=bool(_obj_get(payload_dict, 'livemode', False)),
        )
    except Exception:
        logger.warning(
            'Failed to write billing webhook audit event (event_id=%s, event_type=%s, outcome=%s)',
            event_id,
            event_type,
            outcome,
            exc_info=True,
        )


def record_and_process_webhook_event(event_payload: Any) -> bool:
    payload_dict = _obj_to_dict(event_payload)
    event_id = _obj_get(payload_dict, 'id')
    event_type = _obj_get(payload_dict, 'type') or 'unknown'

    if not event_id:
        raise ClinicBillingProviderError('Stripe event payload missing event id')

    with transaction.atomic():
        webhook_event, created = StripeWebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={
                'event_type': event_type,
                'livemode': bool(_obj_get(payload_dict, 'livemode', False)),
                'payload': payload_dict,
            },
        )

        if not created:
            _audit_webhook_event(
                payload_dict=payload_dict,
                event_id=str(event_id),
                event_type=str(event_type),
                outcome='ignored',
                reason='duplicate_event_id',
            )
            return False

        object_payload = _obj_get(_obj_get(payload_dict, 'data', {}) or {}, 'object', {}) or {}
        clinic = _resolve_clinic_for_event(object_payload)
        ledger_entry = None
        if clinic:
            stripe_subscription_id = (
                _obj_get(object_payload, 'subscription')
                or _obj_get(object_payload, 'id')
                or clinic.stripe_subscription_id
            )
            registration = register_clinic_event(
                clinic=clinic,
                source='webhook',
                event_type=str(event_type),
                event_created_at=stripe_event_created_at(payload_dict),
                idempotency_key=f'webhook:clinic:{event_id}',
                stripe_event_id=str(event_id),
                stripe_subscription_id=str(stripe_subscription_id or ''),
                payload=payload_dict,
            )
            if not registration.should_apply:
                if registration.reason == 'stale':
                    logger.info(
                        'Ignored stale clinic billing webhook event %s (%s)',
                        event_id,
                        event_type,
                    )
                _audit_webhook_event(
                    payload_dict=payload_dict,
                    event_id=str(event_id),
                    event_type=str(event_type),
                    outcome='ignored',
                    reason=registration.reason,
                )
                return True
            ledger_entry = registration.entry

        try:
            process_stripe_event(payload_dict)
            _audit_webhook_event(
                payload_dict=payload_dict,
                event_id=str(event_id),
                event_type=str(event_type),
                outcome='processed',
            )
            mark_event_applied(ledger_entry)
        except Exception:
            logger.exception('Failed to process clinic Stripe webhook event %s', event_id)
            _audit_webhook_event(
                payload_dict=payload_dict,
                event_id=str(event_id),
                event_type=str(event_type),
                outcome='failed',
                reason='processing_exception',
            )
            if ledger_entry:
                ledger_entry.delete()
            webhook_event.delete()
            raise

    return True
