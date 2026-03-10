"""
Ledger helpers for ordered/idempotent billing events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from typing import Any

from django.utils import timezone

from .models import SubscriptionEventLedger


@dataclass(frozen=True)
class LedgerRegistrationResult:
    should_apply: bool
    reason: str
    entry: SubscriptionEventLedger | None


def _obj_get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def stripe_event_created_at(event_payload: Any) -> datetime:
    created_raw = _obj_get(event_payload, 'created')
    if created_raw is None:
        return timezone.now()

    try:
        return datetime.fromtimestamp(int(created_raw), tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        return timezone.now()


def _latest_applied_entry_for_clinic(clinic) -> SubscriptionEventLedger | None:
    return (
        SubscriptionEventLedger.objects.filter(
            object_type=SubscriptionEventLedger.OBJECT_TYPE_CLINIC,
            clinic=clinic,
            status=SubscriptionEventLedger.STATUS_APPLIED,
        )
        .order_by('-event_created_at', '-processed_at')
        .first()
    )


def _latest_applied_entry_for_user(user) -> SubscriptionEventLedger | None:
    return (
        SubscriptionEventLedger.objects.filter(
            object_type=SubscriptionEventLedger.OBJECT_TYPE_INDIVIDUAL,
            user=user,
            status=SubscriptionEventLedger.STATUS_APPLIED,
        )
        .order_by('-event_created_at', '-processed_at')
        .first()
    )


def _register_event(
    *,
    object_type: str,
    clinic=None,
    user=None,
    source: str,
    event_type: str,
    event_created_at: datetime,
    idempotency_key: str,
    stripe_event_id: str | None = None,
    stripe_subscription_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> LedgerRegistrationResult:
    entry, created = SubscriptionEventLedger.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            'object_type': object_type,
            'source': source,
            'clinic': clinic,
            'user': user,
            'event_type': event_type,
            'event_created_at': event_created_at,
            'stripe_event_id': stripe_event_id,
            'stripe_subscription_id': stripe_subscription_id,
            'payload': payload or {},
            'status': SubscriptionEventLedger.STATUS_PENDING,
        },
    )

    if not created:
        return LedgerRegistrationResult(should_apply=False, reason='duplicate', entry=entry)

    if object_type == SubscriptionEventLedger.OBJECT_TYPE_CLINIC:
        latest_applied = _latest_applied_entry_for_clinic(clinic)
    else:
        latest_applied = _latest_applied_entry_for_user(user)

    if latest_applied and event_created_at < latest_applied.event_created_at:
        entry.status = SubscriptionEventLedger.STATUS_IGNORED_STALE
        entry.save(update_fields=['status'])
        return LedgerRegistrationResult(should_apply=False, reason='stale', entry=entry)

    return LedgerRegistrationResult(should_apply=True, reason='ok', entry=entry)


def register_clinic_event(
    *,
    clinic,
    source: str,
    event_type: str,
    event_created_at: datetime,
    idempotency_key: str,
    stripe_event_id: str | None = None,
    stripe_subscription_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> LedgerRegistrationResult:
    return _register_event(
        object_type=SubscriptionEventLedger.OBJECT_TYPE_CLINIC,
        clinic=clinic,
        source=source,
        event_type=event_type,
        event_created_at=event_created_at,
        idempotency_key=idempotency_key,
        stripe_event_id=stripe_event_id,
        stripe_subscription_id=stripe_subscription_id,
        payload=payload,
    )


def register_individual_event(
    *,
    user,
    source: str,
    event_type: str,
    event_created_at: datetime,
    idempotency_key: str,
    stripe_event_id: str | None = None,
    stripe_subscription_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> LedgerRegistrationResult:
    return _register_event(
        object_type=SubscriptionEventLedger.OBJECT_TYPE_INDIVIDUAL,
        user=user,
        source=source,
        event_type=event_type,
        event_created_at=event_created_at,
        idempotency_key=idempotency_key,
        stripe_event_id=stripe_event_id,
        stripe_subscription_id=stripe_subscription_id,
        payload=payload,
    )


def mark_event_applied(entry: SubscriptionEventLedger | None) -> None:
    if not entry:
        return
    entry.status = SubscriptionEventLedger.STATUS_APPLIED
    entry.save(update_fields=['status'])

