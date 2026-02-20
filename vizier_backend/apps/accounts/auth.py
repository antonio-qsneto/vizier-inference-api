"""
AWS Cognito JWT authentication for Django REST Framework.
"""

import logging
from functools import lru_cache

import jwt
import requests
from django.conf import settings
from rest_framework.authentication import TokenAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import User

logger = logging.getLogger(__name__)


class CognitoJWTAuthentication(TokenAuthentication):
    """
    Authenticate using AWS Cognito JWT tokens.

    Token format: Bearer <jwt_token>
    """

    keyword = 'Bearer'

    def authenticate(self, request):
        """
        Authenticate the request using Cognito JWT token.
        """
        auth = get_authorization_header(request).split()

        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None

        if len(auth) == 1:
            msg = 'Invalid token header. No credentials provided.'
            raise AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = 'Invalid token header. Token string should not contain spaces.'
            raise AuthenticationFailed(msg)

        try:
            token = auth[1].decode()
        except UnicodeDecodeError:
            msg = 'Invalid token header. Token string should not contain invalid characters.'
            raise AuthenticationFailed(msg)

        return self.authenticate_credentials(token)

    def authenticate_credentials(self, token: str):
        """
        Validate JWT token and return user.
        """
        try:
            # In development mode without Cognito, create a dummy user
            cognito_pool_id = getattr(settings, 'COGNITO_USER_POOL_ID', '') or ''
            cognito_issuer = getattr(settings, 'COGNITO_ISSUER', '') or ''

            if not cognito_pool_id or not cognito_issuer or 'xxxxxxxxx' in cognito_pool_id:
                # Development mode: create or get dummy user
                from apps.tenants.models import Clinic

                owner, _ = User.objects.get_or_create(
                    cognito_sub='dev-owner',
                    defaults={
                        'email': 'dev-owner@example.com',
                        'first_name': 'Dev',
                        'last_name': 'Owner',
                        'is_active': True,
                        'is_staff': True,
                    }
                )

                clinic, _ = Clinic.objects.get_or_create(
                    name='Development Clinic',
                    defaults={'cnpj': '00000000000191', 'owner': owner}
                )

                user, _ = User.objects.get_or_create(
                    cognito_sub='dev-user',
                    defaults={
                        'email': 'dev@example.com',
                        'first_name': 'Dev',
                        'last_name': 'User',
                        'clinic': clinic,
                        'is_active': True,
                        'is_staff': True,
                    }
                )
                logger.info("Development mode: authenticated as %s", user.email)
                return (user, token)

            claims = self._validate_token(token)

            cognito_sub = claims.get('sub')
            role = claims.get('custom:role', 'INDIVIDUAL')
            clinic_id = claims.get('custom:clinic_id')
            email = self._extract_email_from_claims(claims)

            if not cognito_sub:
                raise AuthenticationFailed('Invalid token claims: missing sub')

            if not email:
                raise AuthenticationFailed('Invalid token claims: missing email/username')

            user, _ = User.objects.update_or_create(
                cognito_sub=cognito_sub,
                defaults={
                    'email': email,
                    'role': role,
                    'is_active': True,
                }
            )

            if clinic_id:
                from apps.tenants.models import Clinic
                try:
                    clinic = Clinic.objects.get(id=clinic_id)
                    user.clinic = clinic
                    user.save(update_fields=['clinic', 'updated_at'])
                except Clinic.DoesNotExist:
                    logger.warning("Clinic %s not found for user %s", clinic_id, email)

            from apps.audit.services import AuditService
            AuditService.log_login(user)

            return (user, token)

        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token: %s", e)
            raise AuthenticationFailed('Invalid token')
        except AuthenticationFailed:
            raise
        except Exception as e:
            logger.error("Authentication error: %s", e, exc_info=True)
            raise AuthenticationFailed('Authentication failed')

    @staticmethod
    def _extract_email_from_claims(claims: dict) -> str | None:
        """
        Resolve an email-like identifier from Cognito claims.

        Access tokens usually don't include `email`; for those we fallback to
        cognito username when it already is an email.
        """
        email = claims.get('email')
        if email:
            return email

        for key in ('cognito:username', 'username'):
            value = claims.get(key)
            if isinstance(value, str) and '@' in value:
                return value

        return None

    @staticmethod
    @lru_cache(maxsize=1)
    def _get_jwks():
        """
        Fetch and cache JWKS from Cognito.
        Cache is valid for 1 hour.
        """
        jwks_url = settings.COGNITO_JWKS_URL
        if not jwks_url:
            raise AuthenticationFailed('Cognito JWKS URL not configured')

        try:
            response = requests.get(jwks_url, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error("Failed to fetch JWKS: %s", e)
            raise AuthenticationFailed('Failed to validate token')

    @staticmethod
    def _validate_token(token: str) -> dict:
        """
        Validate JWT token signature and claims.
        """
        if not all([settings.COGNITO_ISSUER, settings.COGNITO_AUDIENCE]):
            raise AuthenticationFailed('Cognito not configured')

        jwks = CognitoJWTAuthentication._get_jwks()

        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get('kid')
        except jwt.DecodeError:
            raise AuthenticationFailed('Invalid token format')

        key = None
        for k in jwks.get('keys', []):
            if k.get('kid') == kid:
                key = jwt.algorithms.RSAAlgorithm.from_jwk(k)
                break

        if not key:
            raise AuthenticationFailed('Token signing key not found')
        
        # Verify signature/issuer, then validate Cognito audience semantics.
        # Cognito ID tokens carry "aud", while access tokens carry "client_id".
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=['RS256'],
                issuer=settings.COGNITO_ISSUER,
                options={'verify_aud': False},
            )
            CognitoJWTAuthentication._validate_cognito_audience(claims)
            return claims
        except jwt.InvalidIssuerError:
            raise AuthenticationFailed('Invalid token issuer')
        except jwt.InvalidAudienceError:
            raise AuthenticationFailed('Invalid token audience')

    @staticmethod
    def _validate_cognito_audience(claims: dict) -> None:
        """
        Validate audience/client_id based on Cognito token type.
        """
        expected_client_id = getattr(settings, 'COGNITO_AUDIENCE', None)
        if not expected_client_id:
            raise AuthenticationFailed('Cognito not configured')

        token_use = claims.get('token_use')

        if token_use == 'access':
            if claims.get('client_id') != expected_client_id:
                raise AuthenticationFailed('Invalid token audience')
            return

        if token_use == 'id':
            if claims.get('aud') != expected_client_id:
                raise AuthenticationFailed('Invalid token audience')
            return

        # Fallback for non-standard tokens: accept either claim.
        if claims.get('aud') != expected_client_id and claims.get('client_id') != expected_client_id:
            raise AuthenticationFailed('Invalid token audience')
