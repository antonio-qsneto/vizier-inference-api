"""
Study and job models for medical imaging processing.
"""

from django.db import models
from django.utils import timezone
import uuid


class Study(models.Model):
    """
    Medical imaging study model.
    Represents a DICOM upload and its processing pipeline.
    """
    
    STATUS_CHOICES = [
        ('SUBMITTED', 'Submitted'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Ownership
    clinic = models.ForeignKey(
        'tenants.Clinic',
        on_delete=models.CASCADE,
        related_name='studies',
        null=True,
        blank=True,
    )
    owner = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='studies'
    )
    
    # Study details
    category = models.CharField(
        max_length=255,
        help_text='Object category selected by user'
    )
    case_identification = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Case identifier provided by user'
    )
    patient_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Patient name provided by user'
    )
    age = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        help_text='Patient age in years'
    )
    exam_source = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='Exam source provided by user'
    )
    exam_modality = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Exam modality selected by user'
    )
    
    # Processing status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='SUBMITTED'
    )
    
    # Inference integration
    inference_job_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='ID from external inference API'
    )
    
    # Results
    s3_key = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text='S3 path to final NIfTI result'
    )

    # Visualization results (stored separately for frontend overlay)
    image_s3_key = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text='S3 path to image NIfTI for visualization'
    )
    mask_s3_key = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text='S3 path to segmentation NIfTI for visualization'
    )
    
    # Error handling
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text='Error details if processing failed'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'studies_study'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['clinic', 'owner']),
            models.Index(fields=['status']),
            models.Index(fields=['inference_job_id']),
        ]
    
    def __str__(self):
        return f"Study {self.id} - {self.category}"

    def get_owner_scope(self) -> str:
        """
        Return a stable storage scope for this study.

        - Clinic studies: "<clinic_uuid>"
        - Individual studies: "individual/<owner_id>"
        """
        if self.clinic_id:
            return str(self.clinic_id)
        return f"individual/{self.owner_id}"
    
    def is_completed(self):
        """Check if study processing is completed."""
        return self.status == 'COMPLETED'
    
    def is_failed(self):
        """Check if study processing failed."""
        return self.status == 'FAILED'
    
    def mark_completed(self, s3_key):
        """Mark study as completed with S3 result."""
        self.status = 'COMPLETED'
        self.s3_key = s3_key
        self.completed_at = timezone.now()
        self.save()
    
    def mark_failed(self, error_message):
        """Mark study as failed with error message."""
        self.status = 'FAILED'
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save()


class Job(models.Model):
    """
    Job model for tracking inference job status.
    Links to external inference API.
    """
    
    STATUS_CHOICES = [
        ('SUBMITTED', 'Submitted'),
        ('QUEUED', 'Queued'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Study reference
    study = models.OneToOneField(
        Study,
        on_delete=models.CASCADE,
        related_name='job'
    )
    
    # External API reference
    external_job_id = models.CharField(
        max_length=255,
        unique=True,
        help_text='Job ID from external inference API'
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='SUBMITTED'
    )
    
    # Progress
    progress_percent = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'studies_job'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['external_job_id']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Job {self.external_job_id} - {self.status}"
    
    def is_completed(self):
        """Check if job is completed."""
        return self.status == 'COMPLETED'
    
    def is_failed(self):
        """Check if job failed."""
        return self.status == 'FAILED'
    
    def update_status(self, new_status, progress=None):
        """Update job status."""
        self.status = new_status
        if progress is not None:
            self.progress_percent = progress
        if new_status == 'PROCESSING' and not self.started_at:
            self.started_at = timezone.now()
        if new_status == 'COMPLETED':
            self.completed_at = timezone.now()
        self.save()
