"""
Audit logging models for LGPD compliance.
"""

from django.db import models
import uuid


class AuditLog(models.Model):
    """
    Audit log for tracking user actions and system events.
    LGPD compliant: minimal data, no sensitive patient info.
    """
    
    ACTION_CHOICES = [
        ('LOGIN_SEEN', 'Login Seen'),
        ('STUDY_SUBMIT', 'Study Submitted'),
        ('STUDY_STATUS_CHECK', 'Study Status Checked'),
        ('RESULT_DOWNLOAD', 'Result Downloaded'),
        ('DOCTOR_INVITE', 'Doctor Invited'),
        ('DOCTOR_REMOVE', 'Doctor Removed'),
        ('CLINIC_CREATED', 'Clinic Created'),
        ('CLINIC_UPDATED', 'Clinic Updated'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Actor
    clinic = models.ForeignKey(
        'tenants.Clinic',
        on_delete=models.CASCADE,
        related_name='audit_logs'
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    
    # Action
    action = models.CharField(
        max_length=50,
        choices=ACTION_CHOICES
    )
    
    # Resource
    resource_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='ID of affected resource (study_id, user_id, etc.)'
    )
    
    # Details (JSON for flexibility)
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional context about the action'
    )
    
    # Timestamp
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'audit_audit_log'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['clinic', 'timestamp']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action']),
        ]
    
    def __str__(self):
        return f"{self.get_action_display()} by {self.user} at {self.timestamp}"
