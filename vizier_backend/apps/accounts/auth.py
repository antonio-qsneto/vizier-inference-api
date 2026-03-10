"""
AWS Cognito JWT authentication for Django REST Framework.
"""

import logging
from functools import lru_cache

import jwt
import requests
from django.conf import settings
from django.core import signing
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .dev_mock_auth import (
    DEV_MOCK_SUB_PREFIX,
    DEV_MOCK_TOKEN_PREFIX,
    is_dev_mock_auth_enabled,
    parse_dev_mock_access_token,
)
from .models import User
from .rbac import RBACRole, resolve_effective_role

logger = logging.getLogger(__name__)


class CognitoJWTAuthentication(TokenAuthentication):
    """
    Authenticate using AWS Cognito JWT tokens.

    Token format: Bearer <jwt_token>
    """

    keyword = 'Bearer'

    @staticmethod
    def _should_use_development_auth() -> bool:
        if not getattr(settings, 'DEBUG', False):
            return False

        if not getattr(settings, 'ALLOW_INSECURE_DEV_AUTH_FALLBACK', False):
            return False

        if not getattr(settings, 'DEVELOPMENT_MODE', False):
            return False

        cognito_pool_id = getattr(settings, 'COGNITO_USER_POOL_ID', '') or ''
        return not cognito_pool_id or 'xxxxxxxxx' in cognito_pool_id

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
            dev_mock_user = self._authenticate_dev_mock_token(token)
            if dev_mock_user:
                logger.info("Development mock mode: authenticated as %s", dev_mock_user.email)
                return (dev_mock_user, token)

            # In development mode without Cognito, create a dummy user
            if self._should_use_development_auth():
                # Development mode: create or get dummy user
                from apps.tenants.models import Clinic, Membership

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
                if owner.is_deleted():
                    raise AuthenticationFailed('Account has been deleted')

                clinic, _ = Clinic.objects.get_or_create(
                    name='Development Clinic',
                    defaults={'cnpj': '00000000000191', 'owner': owner}
                )
                Membership.objects.get_or_create(
                    account=clinic,
                    user=owner,
                    defaults={'role': Membership.ROLE_ADMIN},
                )

                user, _ = User.objects.get_or_create(
                    cognito_sub='dev-user',
                    defaults={
                        'email': 'dev@example.com',
                        'first_name': 'Dev',
                        'last_name': 'User',
                        'role': 'CLINIC_ADMIN',
                        'clinic': clinic,
                        'is_active': True,
                        'is_staff': True,
                    }
                )
                if user.is_deleted():
                    raise AuthenticationFailed('Account has been deleted')
                if user.clinic_id != clinic.id or user.role != 'CLINIC_ADMIN':
                    user.clinic = clinic
                    user.role = 'CLINIC_ADMIN'
                    user.save(update_fields=['clinic', 'role', 'updated_at'])
                Membership.objects.get_or_create(
                    account=clinic,
                    user=user,
                    defaults={'role': Membership.ROLE_ADMIN},
                )
                logger.info("Development mode: authenticated as %s", user.email)
                return (user, token)

            claims = self._validate_token(token)

            cognito_sub = claims.get('sub')
            token_role = claims.get('custom:role')
            clinic_id = claims.get('custom:clinic_id')
            email = self._extract_email_from_claims(claims)

            if not email:
                # Access tokens can be sparse; try Cognito /oauth2/userInfo.
                email = self._fetch_email_from_userinfo(token)

            if not cognito_sub:
                raise AuthenticationFailed('Invalid token claims: missing sub')

            if not email:
                # Last-resort deterministic identity for local user model.
                email = self._build_fallback_email(cognito_sub)

            email = email.strip().lower()

            # Create or update user but only overwrite role when the token
            # explicitly provides a `custom:role` claim. This prevents JIT
            # provisioning from downgrading a user (e.g. clinic owner) when
            # the token does not include role information.
            user_qs = User.objects.filter(cognito_sub=cognito_sub)
            if not user_qs.exists():
                role_before_update = None
                clinic_before_update = None
                defaults = {
                    'email': email,
                    'is_active': True,
                    'role': token_role or 'INDIVIDUAL',
                }
                user = User.objects.create(cognito_sub=cognito_sub, **defaults)
            else:
                user = user_qs.first()
                if user.is_deleted():
                    raise AuthenticationFailed('Account has been deleted')
                role_before_update = user.role
                clinic_before_update = user.clinic_id
                user.email = email
                if user.account_lifecycle_status == User.ACCOUNT_LIFECYCLE_ACTIVE:
                    user.is_active = True
                # Only update role if the token provides it.
                if token_role:
                    user.role = token_role
                user.save(update_fields=['email', 'is_active', 'role', 'updated_at'])

            if clinic_id:
                from apps.tenants.models import Clinic
                try:
                    clinic = Clinic.objects.get(id=clinic_id)
                    user.clinic = clinic
                    user.save(update_fields=['clinic', 'updated_at'])
                except Clinic.DoesNotExist:
                    logger.warning("Clinic %s not found for user %s", clinic_id, email)

            from apps.audit.services import AuditService
            if (
                token_role
                and role_before_update
                and role_before_update != user.role
                and user.clinic_id
            ):
                AuditService.log_authorization_change(
                    clinic=user.clinic,
                    user=user,
                    change_type='role',
                    resource_id=str(user.id),
                    details={
                        'source': 'cognito_claim',
                        'before': role_before_update,
                        'after': user.role,
                    },
                )
            if (
                clinic_id
                and clinic_before_update != user.clinic_id
                and user.clinic_id
            ):
                AuditService.log_authorization_change(
                    clinic=user.clinic,
                    user=user,
                    change_type='membership',
                    resource_id=str(user.id),
                    details={
                        'source': 'cognito_claim',
                        'before_clinic_id': str(clinic_before_update),
                        'after_clinic_id': str(user.clinic_id),
                    },
                )
            
            # Auto-accept pending invitations for individual users without a clinic.
            if not user.clinic and resolve_effective_role(user) == RBACRole.INDIVIDUAL:
                from apps.tenants.models import DoctorInvitation
                now = timezone.now()

                # Tidy up expired invitations to avoid repeatedly iterating over them.
                DoctorInvitation.objects.filter(
                    email=user.email,
                    status='PENDING',
                    expires_at__lte=now,
                ).update(status='EXPIRED')

                valid_invitations = list(
                    DoctorInvitation.objects.filter(
                        email=user.email,
                        status='PENDING',
                        expires_at__gt=now,
                    ).order_by('-created_at')[:2]
                )

                # Only auto-accept when the match is unambiguous.
                if len(valid_invitations) == 1:
                    invitation = valid_invitations[0]
                    try:
                        from django.db import transaction
                        from apps.tenants.billing import sync_seat_quantity_with_stripe
                        from apps.tenants.models import Membership

                        with transaction.atomic():
                            invitation.accept()
                            user.clinic = invitation.clinic
                            user.role = 'CLINIC_DOCTOR'
                            user.save(update_fields=['clinic', 'role', 'updated_at'])

                            membership, created = Membership.objects.get_or_create(
                                account=invitation.clinic,
                                user=user,
                                defaults={'role': Membership.ROLE_DOCTOR},
                            )
                            if not created and membership.role != Membership.ROLE_DOCTOR:
                                membership.role = Membership.ROLE_DOCTOR
                                membership.save(update_fields=['role', 'updated_at'])

                            if invitation.clinic.stripe_subscription_id:
                                sync_seat_quantity_with_stripe(clinic=invitation.clinic)

                        logger.info(
                            "Auto-accepted invitation %s for %s to clinic %s",
                            invitation.id,
                            user.email,
                            invitation.clinic_id,
                        )
                        AuditService.log_authorization_change(
                            clinic=invitation.clinic,
                            user=user,
                            change_type='membership',
                            resource_id=str(user.id),
                            details={
                                'source': 'invitation_auto_accept',
                                'invitation_id': str(invitation.id),
                                'assigned_role': 'CLINIC_DOCTOR',
                            },
                        )
                    except Exception:
                        logger.error("Failed to auto-accept invitation %s", invitation.id, exc_info=True)

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
    def _authenticate_dev_mock_token(token: str) -> User | None:
        if not is_dev_mock_auth_enabled() or not token.startswith(DEV_MOCK_TOKEN_PREFIX):
            return None

        try:
            user_id = parse_dev_mock_access_token(token)
        except signing.SignatureExpired:
            raise AuthenticationFailed('Development token has expired')
        except (signing.BadSignature, ValueError):
            raise AuthenticationFailed('Invalid development token')

        user = User.objects.filter(
            id=user_id,
            is_active=True,
            cognito_sub__startswith=DEV_MOCK_SUB_PREFIX,
        ).first()
        if not user:
            raise AuthenticationFailed('Invalid development token')

        return user

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
    def _fetch_email_from_userinfo(token: str) -> str | None:
        """
        Fetch email from Cognito userinfo endpoint using access token.
        """
        userinfo_url = getattr(settings, 'COGNITO_USERINFO_URL', None)
        if not userinfo_url:
            return None

        try:
            response = requests.get(
                userinfo_url,
                headers={'Authorization': f'Bearer {token}'},
                timeout=5,
            )
            response.raise_for_status()
            payload = response.json()
            email = payload.get('email')
            if isinstance(email, str) and email:
                return email
        except requests.RequestException as exc:
            logger.warning('Failed to fetch userinfo from Cognito: %s', exc)
        except ValueError:
            logger.warning('Invalid JSON response from Cognito userinfo endpoint')

        return None

    @staticmethod
    def _build_fallback_email(cognito_sub: str) -> str:
        """
        Deterministic synthetic email when Cognito doesn't expose one.
        """
        return f'{cognito_sub}@cognito.local'

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

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=['RS256'],
                issuer=settings.COGNITO_ISSUER,
                leeway=max(0, getattr(settings, 'COGNITO_JWT_LEEWAY_SECONDS', 0)),
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

        if claims.get('aud') != expected_client_id and claims.get('client_id') != expected_client_id:
            raise AuthenticationFailed('Invalid token audience')
