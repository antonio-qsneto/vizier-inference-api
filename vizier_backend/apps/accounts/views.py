"""
Views for accounts app.
"""

import json
import logging

import requests
from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .dev_mock_auth import (
    DEV_MOCK_SUB_PREFIX,
    build_dev_mock_cognito_sub,
    build_dev_mock_token_payload,
    is_dev_mock_auth_enabled,
)
from .models import User
from .serializers import (
    DevMockLoginSerializer,
    DevMockSignupSerializer,
    UserProfileSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)


def _dev_mock_disabled_response() -> Response:
    return Response(
        {'error': 'Development mock authentication is disabled'},
        status=status.HTTP_403_FORBIDDEN,
    )


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for User model."""

    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Filter users based on user's role and clinic.
        
        - Staff/Superuser: see all users
        - Clinic Admin (CLINIC_ADMIN): see users in their clinic
        - Clinic Doctor, Individual Doctor: see only themselves
        """
        user = self.request.user
        
        # Staff/Superuser can see all users
        if user.is_staff or user.is_superuser:
            return User.objects.all()
        
        # Clinic admin can see users in their clinic
        if user.role == 'CLINIC_ADMIN' and user.clinic:
            return User.objects.filter(clinic=user.clinic)
        
        # Clinic doctors, individual doctors, and others see only themselves
        return User.objects.filter(id=user.id)

    @action(detail=False, methods=['get'])
    def me(self, request):
        """
        Get current user profile.
        """
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)


class CategoriesViewSet(viewsets.ViewSet):
    """ViewSet for categories."""

    permission_classes = [IsAuthenticated]

    def list(self, request):
        """
        List all categories.
        """
        try:
            with open(settings.BASE_DIR / 'data' / 'categories.json', 'r') as f:
                categories = json.load(f)
            return Response(categories)
        except Exception as e:
            logger.error("Failed to load categories: %s", e)
            return Response(
                {'error': 'Failed to load categories'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CognitoCallbackView(APIView):
    """
    OAuth callback endpoint for Cognito Authorization Code + PKCE.

    Receives `code` from Cognito and exchanges it for tokens when
    `code_verifier` and `redirect_uri` are provided.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        code = request.query_params.get('code')
        state = request.query_params.get('state')
        error = request.query_params.get('error')
        error_description = request.query_params.get('error_description')

        if error:
            return Response(
                {
                    'error': error,
                    'error_description': error_description,
                    'state': state,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not code:
            return Response(
                {'error': 'Missing authorization code'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        redirect_uri = request.query_params.get('redirect_uri')
        code_verifier = request.query_params.get('code_verifier')

        if not redirect_uri or not code_verifier:
            return Response(
                {
                    'message': 'Authorization code received. Provide redirect_uri and code_verifier to exchange for tokens.',
                    'code': code,
                    'state': state,
                },
                status=status.HTTP_200_OK,
            )

        token_url = getattr(settings, 'COGNITO_TOKEN_URL', None)
        if not token_url:
            return Response(
                {'error': 'COGNITO_TOKEN_URL is not configured'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        payload = {
            'grant_type': 'authorization_code',
            'client_id': settings.COGNITO_CLIENT_ID,
            'code': code,
            'redirect_uri': redirect_uri,
            'code_verifier': code_verifier,
        }

        try:
            response = requests.post(
                token_url,
                data=payload,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=10,
            )
            response.raise_for_status()
            token_response = response.json()
        except requests.RequestException as exc:
            body = getattr(getattr(exc, 'response', None), 'text', '')
            logger.warning('Cognito callback token exchange failed: %s', body or exc)
            return Response(
                {
                    'error': 'Token exchange failed',
                    'details': body or str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'message': 'Token exchange successful',
                'state': state,
                'tokens': token_response,
            },
            status=status.HTTP_200_OK,
        )


class DevMockSignupView(APIView):
    """Create a local development user and issue a mock access token."""

    permission_classes = [AllowAny]

    def post(self, request):
        if not is_dev_mock_auth_enabled():
            return _dev_mock_disabled_response()

        serializer = DevMockSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        email = payload['email']
        if User.objects.filter(email=email).exists():
            return Response(
                {'email': ['A user with this email already exists.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User(
            email=email,
            cognito_sub=build_dev_mock_cognito_sub(),
            first_name=payload.get('first_name', ''),
            last_name=payload.get('last_name', ''),
            role='INDIVIDUAL',
            is_active=True,
        )
        user.set_password(payload['password'])
        user.save()

        return Response(
            build_dev_mock_token_payload(user.id),
            status=status.HTTP_201_CREATED,
        )


class DevMockLoginView(APIView):
    """Authenticate an existing development user and issue a mock token."""

    permission_classes = [AllowAny]

    def post(self, request):
        if not is_dev_mock_auth_enabled():
            return _dev_mock_disabled_response()

        serializer = DevMockLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        user = User.objects.filter(
            email=payload['email'],
            cognito_sub__startswith=DEV_MOCK_SUB_PREFIX,
            is_active=True,
        ).first()
        if not user or not user.check_password(payload['password']):
            return Response(
                {'non_field_errors': ['Invalid email or password']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            build_dev_mock_token_payload(user.id),
            status=status.HTTP_200_OK,
        )
