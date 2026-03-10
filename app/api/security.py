import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from settings import settings

bearer_scheme = HTTPBearer(auto_error=False)


def require_api_bearer_auth(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> str | None:
    """
    Protect API routes with explicit bearer authentication.

    When API_AUTH_ENABLED=false, requests are allowed without token (local/internal use).
    """
    if not settings.API_AUTH_ENABLED:
        return None

    expected_token = (settings.API_AUTH_BEARER_TOKEN or "").strip()
    if not expected_token:
        # Startup check should prevent this, but keep a defensive fail-closed guard.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Inference API authentication is misconfigured",
        )

    if not credentials or (credentials.scheme or "").lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not secrets.compare_digest(credentials.credentials, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials
