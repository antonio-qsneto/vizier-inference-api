"""
Health check views.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Health check endpoint.
    Returns 200 OK if service is healthy.
    """
    return Response(
        {
            'status': 'healthy',
            'service': 'vizier-med-backend',
            'version': '1.0.0',
        },
        status=status.HTTP_200_OK
    )
