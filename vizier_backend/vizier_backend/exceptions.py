"""
Custom exception handlers for DRF.
"""

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that logs errors and returns structured responses.
    """
    response = exception_handler(exc, context)
    
    if response is None:
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return Response(
            {
                'error': 'Internal server error',
                'detail': str(exc) if not isinstance(exc, Exception) else 'An unexpected error occurred',
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    # Log the error
    logger.warning(
        f"API Error: {exc.__class__.__name__}",
        extra={
            'status_code': response.status_code,
            'detail': str(response.data),
        }
    )
    
    return response
