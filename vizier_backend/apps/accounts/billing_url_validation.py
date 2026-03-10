"""
Validation helpers for Stripe redirect/return URLs.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from django.conf import settings


class BillingRedirectURLError(ValueError):
    """Raised when a billing redirect URL is invalid or not allowed."""


def _normalize_origin(url: str) -> tuple[str, str, int]:
    parsed = urlparse((url or '').strip())
    scheme = (parsed.scheme or '').lower()
    if scheme not in {'http', 'https'}:
        raise BillingRedirectURLError('Only http/https redirect URLs are allowed')

    hostname = (parsed.hostname or '').strip().lower()
    if not hostname:
        raise BillingRedirectURLError('Redirect URL must include a hostname')

    if parsed.port is not None:
        port = int(parsed.port)
    elif scheme == 'https':
        port = 443
    else:
        port = 80

    return (scheme, hostname, port)


@lru_cache(maxsize=16)
def _allowed_redirect_origins_from_config(
    configured: tuple[str, ...],
) -> set[tuple[str, str, int]]:
    origins: set[tuple[str, str, int]] = set()

    for raw_origin in configured:
        origin_text = str(raw_origin or '').strip()
        if not origin_text:
            continue
        origins.add(_normalize_origin(origin_text))

    return origins


def allowed_redirect_origins() -> set[tuple[str, str, int]]:
    configured = getattr(settings, 'STRIPE_ALLOWED_REDIRECT_ORIGINS', None) or []
    normalized_config = tuple(str(item) for item in configured)
    return _allowed_redirect_origins_from_config(normalized_config)


def validate_redirect_url(url: str, *, field_name: str) -> str:
    try:
        candidate = _normalize_origin(url)
    except BillingRedirectURLError as exc:
        raise BillingRedirectURLError(f'{field_name}: {exc}') from exc

    if candidate not in allowed_redirect_origins():
        raise BillingRedirectURLError(
            f'{field_name}: redirect origin is not allowed by STRIPE_ALLOWED_REDIRECT_ORIGINS'
        )

    return url
