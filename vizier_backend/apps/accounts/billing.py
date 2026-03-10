"""
Stripe billing helpers for individual-user subscriptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
import hashlib
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import UserSubscription
from apps.tenants.billing_ledger import mark_event_applied, register_individual_event


class BillingConfigurationError(Exception):
    """Raised when billing is misconfigured."""


class BillingProviderError(Exception):
    """Raised when Stripe provider operations fail."""


@dataclass(frozen=True)
class BillingPlanDefinition:
    id: str
    label: str
    price_label: str
    summary: str
    interval: str
    currency: str
    amount_cents: int


PLAN_DEFINITIONS = {
    UserSubscription.PLAN_INDIVIDUAL_MONTHLY: BillingPlanDefinition(
        id=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
        label='Plano individual mensal',
        price_label='R$ 679,00/mês',
        summary='Acesso individual com upload e histórico de estudos.',
        interval='month',
        currency='brl',
        amount_cents=67900,
    ),
    UserSubscription.PLAN_INDIVIDUAL_ANNUAL: BillingPlanDefinition(
        id=UserSubscription.PLAN_INDIVIDUAL_ANNUAL,
        label='Plano individual anual',
        price_label='R$ 7.333,00/ano',
        summary='Acesso individual anual com cobrança reduzida.',
        interval='year',
        currency='brl',
        amount_cents=733300,
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


def configured_dunning_grace_days() -> int:
    raw = getattr(settings, 'BILLING_DUNNING_GRACE_DAYS', 7)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 7


def compute_grace_until(reference_dt: datetime | None = None) -> datetime:
    reference_dt = reference_dt or timezone.now()
    return reference_dt + timedelta(days=configured_dunning_grace_days())


def get_plan_definition(plan_id: str) -> BillingPlanDefinition:
    if plan_id not in PLAN_DEFINITIONS:
        raise BillingConfigurationError(f'Unsupported plan_id: {plan_id}')
    return PLAN_DEFINITIONS[plan_id]


def list_individual_billing_plans() -> list[dict[str, Any]]:
    return [
        {
            'id': plan.id,
            'label': plan.label,
            'price_label': plan.price_label,
            'summary': plan.summary,
            'interval': plan.interval,
        }
        for plan in PLAN_DEFINITIONS.values()
    ]


def _get_stripe_sdk():
    try:
        import stripe
    except ImportError as exc:
        raise BillingConfigurationError('stripe package is not installed') from exc
    return stripe


def _get_stripe_secret_key() -> str:
    key = (
        getattr(settings, 'STRIPE_SECRET_KEY', None)
        or getattr(settings, 'STRIPE_API_KEY', None)
    )
    if not key:
        raise BillingConfigurationError('Missing Stripe secret key')
    return key


def _explicit_price_id_for_plan(plan_id: str) -> str | None:
    if plan_id == UserSubscription.PLAN_INDIVIDUAL_MONTHLY:
        return getattr(settings, 'STRIPE_PRICE_ID_INDIVIDUAL_MONTHLY', None)
    if plan_id == UserSubscription.PLAN_INDIVIDUAL_ANNUAL:
        return getattr(settings, 'STRIPE_PRICE_ID_INDIVIDUAL_ANNUAL', None)
    return None


def _lookup_key_for_plan(plan_id: str) -> str | None:
    if plan_id == UserSubscription.PLAN_INDIVIDUAL_MONTHLY:
        return getattr(settings, 'STRIPE_PRICE_LOOKUP_KEY_INDIVIDUAL_MONTHLY', None)
    if plan_id == UserSubscription.PLAN_INDIVIDUAL_ANNUAL:
        return getattr(settings, 'STRIPE_PRICE_LOOKUP_KEY_INDIVIDUAL_ANNUAL', None)
    return None


def _resolve_price_id_from_lookup_key(stripe_module, lookup_key: str) -> str | None:
    try:
        prices = stripe_module.Price.list(lookup_keys=[lookup_key], active=True, limit=1)
    except Exception as exc:
        raise BillingProviderError(
            f'Failed to resolve Stripe price by lookup key "{lookup_key}": {exc}'
        ) from exc

    entries = _obj_get(prices, 'data', []) or []
    if not entries:
        return None

    price_id = _obj_get(entries[0], 'id')
    if not price_id:
        return None
    return str(price_id)


def _infer_price_id_from_product(stripe_module, plan: BillingPlanDefinition) -> str:
    product_id = getattr(settings, 'STRIPE_PRODUCT_ID', None)
    if not product_id:
        raise BillingConfigurationError('Missing STRIPE_PRODUCT_ID')

    try:
        prices = stripe_module.Price.list(product=product_id, active=True, limit=100)
    except Exception as exc:
        raise BillingProviderError(f'Failed to list Stripe prices: {exc}') from exc

    candidates = []
    for price in _obj_get(prices, 'data', []) or []:
        recurring = _obj_get(price, 'recurring', {}) or {}
        interval = _obj_get(recurring, 'interval')
        currency = str(_obj_get(price, 'currency', '') or '').lower()
        if interval != plan.interval:
            continue
        if currency and currency != plan.currency.lower():
            continue
        candidates.append(price)

    if not candidates:
        raise BillingConfigurationError(
            f'No active Stripe prices found for interval={plan.interval} on product {product_id}'
        )

    exact_amount_match = [
        price for price in candidates if _obj_get(price, 'unit_amount') == plan.amount_cents
    ]
    selected = exact_amount_match[0] if exact_amount_match else candidates[0]
    selected_price_id = _obj_get(selected, 'id')
    if not selected_price_id:
        raise BillingConfigurationError('Selected Stripe price has no id')

    return str(selected_price_id)


def resolve_price_id(plan_id: str, stripe_module=None) -> str:
    explicit_price_id = _explicit_price_id_for_plan(plan_id)
    if explicit_price_id:
        return explicit_price_id

    stripe_module = stripe_module or _get_stripe_sdk()
    stripe_module.api_key = _get_stripe_secret_key()

    lookup_key = _lookup_key_for_plan(plan_id)
    if lookup_key:
        lookup_price_id = _resolve_price_id_from_lookup_key(stripe_module, lookup_key)
        if lookup_price_id:
            return lookup_price_id

    plan = get_plan_definition(plan_id)
    return _infer_price_id_from_product(stripe_module, plan)


def create_checkout_session(
    *,
    user_id: int,
    user_email: str,
    plan_id: str,
    success_url: str,
    cancel_url: str,
):
    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()

    price_id = resolve_price_id(plan_id, stripe_module=stripe)

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(user_id),
            customer_email=user_email,
            metadata={
                'user_id': str(user_id),
                'plan_id': plan_id,
            },
            allow_promotion_codes=True,
        )
    except Exception as exc:
        raise BillingProviderError(f'Failed to create Stripe checkout session: {exc}') from exc

    return checkout_session, price_id


def update_subscription_plan(
    *,
    subscription_id: str,
    plan_id: str,
    proration_behavior: str = 'create_prorations',
):
    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()

    price_id = resolve_price_id(plan_id, stripe_module=stripe)

    try:
        current_subscription = stripe.Subscription.retrieve(subscription_id)
    except Exception as exc:
        raise BillingProviderError(f'Failed to retrieve Stripe subscription for update: {exc}') from exc

    items = _obj_get(_obj_get(current_subscription, 'items', {}) or {}, 'data', []) or []
    if not items:
        raise BillingProviderError('Stripe subscription has no items to update')

    subscription_item_id = _obj_get(items[0], 'id')
    if not subscription_item_id:
        raise BillingProviderError('Stripe subscription item missing id')

    try:
        updated_subscription = stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=False,
            proration_behavior=proration_behavior,
            items=[{'id': subscription_item_id, 'price': price_id}],
            metadata={'plan_id': plan_id},
        )
    except Exception as exc:
        raise BillingProviderError(f'Failed to update Stripe subscription plan: {exc}') from exc

    return updated_subscription, price_id


def create_customer_portal_session(*, customer_id: str, return_url: str):
    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()

    try:
        return stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
    except Exception as exc:
        raise BillingProviderError(f'Failed to create Stripe customer portal session: {exc}') from exc


def cancel_subscription_at_period_end(*, subscription_id: str):
    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()

    try:
        return stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True,
            proration_behavior='none',
        )
    except Exception as exc:
        raise BillingProviderError(f'Failed to cancel Stripe subscription at period end: {exc}') from exc


def construct_webhook_event(*, payload: bytes, signature: str):
    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)
    if not webhook_secret:
        raise BillingConfigurationError('Missing STRIPE_WEBHOOK_SECRET')

    try:
        return stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=webhook_secret,
        )
    except Exception as exc:
        raise BillingProviderError(f'Invalid Stripe webhook signature/payload: {exc}') from exc


def retrieve_subscription(subscription_id: str):
    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()
    try:
        return stripe.Subscription.retrieve(subscription_id)
    except Exception as exc:
        raise BillingProviderError(f'Failed to retrieve Stripe subscription: {exc}') from exc


def retrieve_checkout_session(checkout_session_id: str):
    stripe = _get_stripe_sdk()
    stripe.api_key = _get_stripe_secret_key()
    try:
        return stripe.checkout.Session.retrieve(checkout_session_id)
    except Exception as exc:
        raise BillingProviderError(f'Failed to retrieve Stripe checkout session: {exc}') from exc


def normalize_subscription_status(stripe_status: str | None) -> str:
    normalized = (stripe_status or '').strip().lower()
    if normalized == 'active':
        return UserSubscription.STATUS_ACTIVE
    if normalized == 'trialing':
        return UserSubscription.STATUS_TRIALING
    if normalized in {'past_due', 'unpaid'}:
        return UserSubscription.STATUS_PAST_DUE
    if normalized in {'incomplete', 'incomplete_expired'}:
        return UserSubscription.STATUS_INCOMPLETE
    if normalized in {'canceled', 'cancelled'}:
        return UserSubscription.STATUS_CANCELED
    return UserSubscription.STATUS_INACTIVE


def timestamp_to_datetime(value: Any):
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def extract_subscription_price_id(subscription_payload: Any) -> str | None:
    items = _obj_get(_obj_get(subscription_payload, 'items', {}) or {}, 'data', []) or []
    if not items:
        return None

    first_item = items[0]
    price = _obj_get(first_item, 'price', {}) or {}
    return _obj_get(price, 'id')


def infer_plan_id_from_price_id(price_id: str | None) -> str | None:
    if not price_id:
        return None

    monthly = getattr(settings, 'STRIPE_PRICE_ID_INDIVIDUAL_MONTHLY', None)
    annual = getattr(settings, 'STRIPE_PRICE_ID_INDIVIDUAL_ANNUAL', None)
    if monthly and price_id == monthly:
        return UserSubscription.PLAN_INDIVIDUAL_MONTHLY
    if annual and price_id == annual:
        return UserSubscription.PLAN_INDIVIDUAL_ANNUAL

    # Fallback by recurring interval when explicit price IDs are not configured.
    try:
        stripe = _get_stripe_sdk()
        stripe.api_key = _get_stripe_secret_key()
    except BillingConfigurationError:
        return None
    try:
        price = stripe.Price.retrieve(price_id)
    except Exception:
        return None

    recurring = _obj_get(price, 'recurring', {}) or {}
    interval = _obj_get(recurring, 'interval')
    if interval == 'month':
        return UserSubscription.PLAN_INDIVIDUAL_MONTHLY
    if interval == 'year':
        return UserSubscription.PLAN_INDIVIDUAL_ANNUAL
    return None


def apply_subscription_payload(
    *,
    subscription: UserSubscription,
    stripe_subscription_payload: Any,
    fallback_plan_id: str | None = None,
    event_created_at: datetime | None = None,
) -> UserSubscription:
    stripe_status = _obj_get(stripe_subscription_payload, 'status')
    stripe_subscription_id = _obj_get(stripe_subscription_payload, 'id')
    stripe_customer_id = _obj_get(stripe_subscription_payload, 'customer')
    cancel_at_period_end = bool(_obj_get(stripe_subscription_payload, 'cancel_at_period_end', False))
    current_period_end = timestamp_to_datetime(
        _obj_get(stripe_subscription_payload, 'current_period_end')
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
    normalized_status = normalize_subscription_status(stripe_status)
    if cancel_at_period_end and normalized_status in {
        UserSubscription.STATUS_ACTIVE,
        UserSubscription.STATUS_TRIALING,
        UserSubscription.STATUS_PAST_DUE,
    }:
        normalized_status = UserSubscription.STATUS_CANCELED
    subscription.status = normalized_status
    if stripe_subscription_id:
        subscription.stripe_subscription_id = stripe_subscription_id
    if stripe_customer_id:
        subscription.stripe_customer_id = stripe_customer_id
    if price_id:
        subscription.stripe_price_id = price_id
    subscription.current_period_end = current_period_end
    subscription.cancel_at_period_end = cancel_at_period_end

    if subscription.status == UserSubscription.STATUS_CANCELED:
        if not subscription.canceled_at:
            subscription.canceled_at = event_created_at or timezone.now()
    elif not cancel_at_period_end:
        subscription.canceled_at = None

    if subscription.status == UserSubscription.STATUS_PAST_DUE:
        computed_grace_until = compute_grace_until(event_created_at)
        if (
            not subscription.billing_grace_until
            or subscription.billing_grace_until < computed_grace_until
        ):
            subscription.billing_grace_until = computed_grace_until
    elif subscription.status in {UserSubscription.STATUS_ACTIVE, UserSubscription.STATUS_TRIALING}:
        subscription.billing_grace_until = None
    elif subscription.status in {
        UserSubscription.STATUS_CANCELED,
        UserSubscription.STATUS_INACTIVE,
    }:
        subscription.billing_grace_until = None

    subscription.save()
    return subscription


def subscription_state_fingerprint(subscription_payload: Any) -> str:
    signature = '|'.join(
        [
            str(_obj_get(subscription_payload, 'id') or ''),
            str(_obj_get(subscription_payload, 'status') or ''),
            str(_obj_get(subscription_payload, 'current_period_end') or ''),
            str(extract_subscription_price_id(subscription_payload) or ''),
        ]
    )
    return hashlib.sha256(signature.encode('utf-8')).hexdigest()[:24]


def reconcile_individual_subscription_state(*, subscription: UserSubscription) -> bool:
    stripe_subscription_id = subscription.stripe_subscription_id
    if not stripe_subscription_id:
        return False

    stripe_subscription_payload = retrieve_subscription(stripe_subscription_id)
    event_created_at = timezone.now()
    idempotency_key = (
        f"reconcile:individual:{subscription.user_id}:"
        f"{subscription_state_fingerprint(stripe_subscription_payload)}"
    )
    registration = register_individual_event(
        user=subscription.user,
        source='reconciliation',
        event_type='subscription.snapshot',
        event_created_at=event_created_at,
        idempotency_key=idempotency_key,
        stripe_event_id=None,
        stripe_subscription_id=str(stripe_subscription_id),
        payload=_obj_to_dict(stripe_subscription_payload),
    )
    if not registration.should_apply:
        return False

    ledger_entry = registration.entry
    try:
        apply_subscription_payload(
            subscription=subscription,
            stripe_subscription_payload=stripe_subscription_payload,
            fallback_plan_id=subscription.plan,
            event_created_at=event_created_at,
        )
        mark_event_applied(ledger_entry)
        return True
    except Exception:
        if ledger_entry:
            ledger_entry.delete()
        raise
