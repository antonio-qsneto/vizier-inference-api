"""
Views for accounts app.
"""

import json
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.conf import settings
from .models import User
from .serializers import UserSerializer, UserProfileSerializer
import logging

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
            logger.error(f"Failed to load categories: {e}")
            return Response(
                {'error': 'Failed to load categories'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
