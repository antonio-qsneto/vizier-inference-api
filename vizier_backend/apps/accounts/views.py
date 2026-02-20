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

from .models import User
from .serializers import UserProfileSerializer, UserSerializer

logger = logging.getLogger(__name__)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for User model."""

    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

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
