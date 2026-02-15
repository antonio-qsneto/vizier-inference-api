"""
Audit logging service for LGPD compliance.
"""

from django.utils import timezone
from .models import AuditLog
import logging

logger = logging.getLogger(__name__)


class AuditService:
    """Service for logging audit events."""
    
    @staticmethod
    def log_action(
        clinic,
        action: str,
        user=None,
        resource_id: str = None,
        details: dict = None
    ) -> AuditLog:
        """
        Log an audit action.
        
        Args:
            clinic: Clinic instance
            action: Action type (from AuditLog.ACTION_CHOICES)
            user: User instance (optional)
            resource_id: ID of affected resource (optional)
            details: Additional context as dict (optional)
        
        Returns:
            AuditLog instance
        """
        try:
            audit_log = AuditLog.objects.create(
                clinic=clinic,
                user=user,
                action=action,
                resource_id=resource_id,
                details=details or {}
            )
            logger.info(
                f"Audit: {action} by {user} in {clinic}",
                extra={'audit_log_id': str(audit_log.id)}
            )
            return audit_log
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}", exc_info=True)
            raise
    
    @staticmethod
    def log_login(user):
        """Log user login."""
        if user.clinic:
            AuditService.log_action(
                clinic=user.clinic,
                action='LOGIN_SEEN',
                user=user,
                details={'email': user.email}
            )
    
    @staticmethod
    def log_study_submit(study):
        """Log study submission."""
        AuditService.log_action(
            clinic=study.clinic,
            action='STUDY_SUBMIT',
            user=study.owner,
            resource_id=str(study.id),
            details={'category': study.category}
        )
    
    @staticmethod
    def log_study_status_check(study):
        """Log study status check."""
        AuditService.log_action(
            clinic=study.clinic,
            action='STUDY_STATUS_CHECK',
            user=None,  # Could be system or user
            resource_id=str(study.id),
            details={'status': study.status}
        )
    
    @staticmethod
    def log_result_download(study, user):
        """Log result download."""
        AuditService.log_action(
            clinic=study.clinic,
            action='RESULT_DOWNLOAD',
            user=user,
            resource_id=str(study.id),
            details={
                'image_s3_key': getattr(study, 'image_s3_key', None),
                'mask_s3_key': getattr(study, 'mask_s3_key', None),
                'legacy_s3_key': getattr(study, 's3_key', None),
            }
        )
    
    @staticmethod
    def log_doctor_invite(clinic, invited_by, email):
        """Log doctor invitation."""
        AuditService.log_action(
            clinic=clinic,
            action='DOCTOR_INVITE',
            user=invited_by,
            details={'invited_email': email}
        )
    
    @staticmethod
    def log_doctor_remove(clinic, removed_by, doctor):
        """Log doctor removal."""
        AuditService.log_action(
            clinic=clinic,
            action='DOCTOR_REMOVE',
            user=removed_by,
            resource_id=str(doctor.id),
            details={'doctor_email': doctor.email}
        )
