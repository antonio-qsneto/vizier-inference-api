"""
Helpers for development-only mock authentication.
"""

from uuid import uuid4

from django.conf import settings
from django.core import signing

DEV_MOCK_TOKEN_PREFIX = 'devmock.'
DEV_MOCK_SUB_PREFIX = 'devmock-user-'
_DEFAULT_TOKEN_MAX_AGE_SECONDS = 12 * 60 * 60


def is_dev_mock_auth_enabled() -> bool:
    return bool(getattr(settings, 'DEV_MOCK_AUTH_ENABLED', False))


def get_dev_mock_token_max_age_seconds() -> int:
    raw_value = getattr(settings, 'DEV_MOCK_TOKEN_MAX_AGE_SECONDS', _DEFAULT_TOKEN_MAX_AGE_SECONDS)

    try:
        parsed_value = int(raw_value)
    except (TypeError, ValueError):
        parsed_value = _DEFAULT_TOKEN_MAX_AGE_SECONDS

    return max(60, parsed_value)


def build_dev_mock_cognito_sub() -> str:
    return f'{DEV_MOCK_SUB_PREFIX}{uuid4().hex}'


def issue_dev_mock_access_token(user_id: int) -> str:
    signer = signing.TimestampSigner(salt='vizier.accounts.dev-mock-auth')
    payload = signer.sign(str(user_id))
    return f'{DEV_MOCK_TOKEN_PREFIX}{payload}'


def parse_dev_mock_access_token(token: str) -> int:
    if not token.startswith(DEV_MOCK_TOKEN_PREFIX):
        raise signing.BadSignature('Invalid dev mock token prefix')

    signer = signing.TimestampSigner(salt='vizier.accounts.dev-mock-auth')
    signed_payload = token[len(DEV_MOCK_TOKEN_PREFIX):]
    raw_user_id = signer.unsign(
        signed_payload,
        max_age=get_dev_mock_token_max_age_seconds(),
    )
    return int(raw_user_id)


def build_dev_mock_token_payload(user_id: int) -> dict:
    return {
        'access_token': issue_dev_mock_access_token(user_id),
        'expires_in': get_dev_mock_token_max_age_seconds(),
        'token_type': 'Bearer',
        'auth_mode': 'dev_mock',
    }
