"""Domain models for async S3-first inference pipeline."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

TENANT_TYPE_CLINIC = "CLINIC"
TENANT_TYPE_INDIVIDUAL = "INDIVIDUAL"
TENANT_TYPE_CHOICES = [
    (TENANT_TYPE_CLINIC, "Clinic"),
    (TENANT_TYPE_INDIVIDUAL, "Individual"),
]


class Tenant(models.Model):
    """Logical tenant boundary used by inference jobs."""

    TYPE_CLINIC = TENANT_TYPE_CLINIC
    TYPE_INDIVIDUAL = TENANT_TYPE_INDIVIDUAL
    TYPE_CHOICES = TENANT_TYPE_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    clinic = models.ForeignKey(
        "tenants.Clinic",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inference_tenants",
    )
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="owned_inference_tenants",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inference_tenant"
        indexes = [
            models.Index(fields=["type", "is_active"]),
            models.Index(fields=["clinic"]),
            models.Index(fields=["owner_user"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    (
                        models.Q(type=TENANT_TYPE_CLINIC, clinic__isnull=False)
                        & models.Q(owner_user__isnull=True)
                    )
                    | (
                        models.Q(type=TENANT_TYPE_INDIVIDUAL, owner_user__isnull=False)
                        & models.Q(clinic__isnull=True)
                    )
                ),
                name="inference_tenant_shape_constraint",
            ),
            models.UniqueConstraint(
                fields=["clinic"],
                condition=models.Q(clinic__isnull=False),
                name="inference_tenant_unique_clinic",
            ),
            models.UniqueConstraint(
                fields=["owner_user"],
                condition=models.Q(owner_user__isnull=False),
                name="inference_tenant_unique_owner_user",
            ),
        ]

    def __str__(self) -> str:
        if self.type == self.TYPE_CLINIC:
            return f"Tenant(clinic={self.clinic_id})"
        return f"Tenant(individual={self.owner_user_id})"

    @classmethod
    def resolve_for_user(cls, user):
        if getattr(user, "clinic_id", None):
            tenant, _ = cls.objects.get_or_create(
                clinic_id=user.clinic_id,
                defaults={
                    "type": cls.TYPE_CLINIC,
                    "owner_user": None,
                    "is_active": True,
                },
            )
            return tenant

        tenant, _ = cls.objects.get_or_create(
            owner_user_id=user.id,
            defaults={
                "type": cls.TYPE_INDIVIDUAL,
                "clinic": None,
                "is_active": True,
            },
        )
        return tenant


class ModelVersion(models.Model):
    """Model version catalog used to route inference jobs."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    version = models.CharField(max_length=64)
    executor = models.CharField(max_length=64, default="biomedparse")
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inference_model_version"
        indexes = [
            models.Index(fields=["name", "version"]),
            models.Index(fields=["executor", "is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "version"],
                name="inference_model_version_unique_name_version",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name}:{self.version}"


class InferenceJob(models.Model):
    """Inference job metadata/state tracked in PostgreSQL."""

    STATUS_CREATED = "CREATED"
    STATUS_UPLOAD_PENDING = "UPLOAD_PENDING"
    STATUS_UPLOADED = "UPLOADED"
    STATUS_VALIDATING = "VALIDATING"
    STATUS_PREPROCESSING = "PREPROCESSING"
    STATUS_QUEUED = "QUEUED"
    STATUS_RUNNING = "RUNNING"
    STATUS_POSTPROCESSING = "POSTPROCESSING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"

    STATUS_CHOICES = [
        (STATUS_CREATED, "Created"),
        (STATUS_UPLOAD_PENDING, "Upload pending"),
        (STATUS_UPLOADED, "Uploaded"),
        (STATUS_VALIDATING, "Validating"),
        (STATUS_PREPROCESSING, "Preprocessing"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Running"),
        (STATUS_POSTPROCESSING, "Postprocessing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    TERMINAL_STATUSES = {STATUS_COMPLETED, STATUS_FAILED}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="jobs",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inference_jobs",
    )
    study = models.ForeignKey(
        "studies.Study",
        on_delete=models.SET_NULL,
        related_name="inference_jobs",
        null=True,
        blank=True,
    )
    requested_model_version = models.ForeignKey(
        ModelVersion,
        on_delete=models.SET_NULL,
        related_name="jobs",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_CREATED)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    requested_device = models.CharField(max_length=32, default="cuda")
    slice_batch_size = models.PositiveSmallIntegerField(null=True, blank=True)
    gpu_task_arn = models.CharField(max_length=512, null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)

    idempotency_key = models.CharField(max_length=255, null=True, blank=True)
    correlation_id = models.CharField(max_length=255, db_index=True)

    request_payload = models.JSONField(default=dict, blank=True)

    error_type = models.CharField(max_length=128, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    uploaded_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "inference_job"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["owner", "created_at"]),
            models.Index(fields=["status", "updated_at"]),
            models.Index(fields=["idempotency_key"]),
            models.Index(fields=["requested_device"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False),
                name="inference_job_unique_tenant_idempotency",
            )
        ]

    def __str__(self) -> str:
        return f"{self.id} ({self.status})"

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES

    def mark_running_timestamps(self) -> None:
        if not self.started_at:
            self.started_at = timezone.now()

    def mark_completed_timestamps(self) -> None:
        self.completed_at = timezone.now()


class InputArtifact(models.Model):
    """Input objects used by a job."""

    KIND_RAW_UPLOAD = "RAW_UPLOAD"
    KIND_NORMALIZED_INPUT = "NORMALIZED_INPUT"
    KIND_CHOICES = [
        (KIND_RAW_UPLOAD, "Raw upload"),
        (KIND_NORMALIZED_INPUT, "Normalized input"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_UPLOADED = "UPLOADED"
    STATUS_VALIDATED = "VALIDATED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_UPLOADED, "Uploaded"),
        (STATUS_VALIDATED, "Validated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        InferenceJob,
        on_delete=models.CASCADE,
        related_name="input_artifacts",
    )
    bucket = models.CharField(max_length=255)
    key = models.CharField(max_length=1024)
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)

    original_filename = models.CharField(max_length=512, null=True, blank=True)
    content_type = models.CharField(max_length=255, null=True, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    etag = models.CharField(max_length=128, null=True, blank=True)
    checksum_sha256 = models.CharField(max_length=128, null=True, blank=True)
    upload_status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)

    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inference_input_artifact"
        indexes = [
            models.Index(fields=["job", "kind"]),
            models.Index(fields=["bucket", "key"]),
            models.Index(fields=["upload_status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "kind"],
                name="inference_input_artifact_unique_job_kind",
            )
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.bucket}/{self.key}"


class OutputArtifact(models.Model):
    """Output objects produced by a job."""

    KIND_NORMALIZED_INPUT_NPZ = "NORMALIZED_INPUT_NPZ"
    KIND_ORIGINAL_NIFTI = "ORIGINAL_NIFTI"
    KIND_MASK_NIFTI = "MASK_NIFTI"
    KIND_SUMMARY_JSON = "SUMMARY_JSON"
    KIND_EXTRA = "EXTRA"

    KIND_CHOICES = [
        (KIND_NORMALIZED_INPUT_NPZ, "Normalized input NPZ"),
        (KIND_ORIGINAL_NIFTI, "Original NIfTI"),
        (KIND_MASK_NIFTI, "Mask NIfTI"),
        (KIND_SUMMARY_JSON, "Summary JSON"),
        (KIND_EXTRA, "Extra artifact"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        InferenceJob,
        on_delete=models.CASCADE,
        related_name="output_artifacts",
    )
    bucket = models.CharField(max_length=255)
    key = models.CharField(max_length=1024)
    kind = models.CharField(max_length=64, choices=KIND_CHOICES)
    content_type = models.CharField(max_length=255, null=True, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    etag = models.CharField(max_length=128, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inference_output_artifact"
        indexes = [
            models.Index(fields=["job", "kind"]),
            models.Index(fields=["bucket", "key"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "kind"],
                name="inference_output_artifact_unique_job_kind",
            )
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.bucket}/{self.key}"


class JobStatusHistory(models.Model):
    """Immutable audit trail for job state transitions."""

    id = models.BigAutoField(primary_key=True)
    job = models.ForeignKey(
        InferenceJob,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    from_status = models.CharField(max_length=32, null=True, blank=True)
    to_status = models.CharField(max_length=32)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inference_status_history_events",
    )
    reason = models.CharField(max_length=255, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inference_job_status_history"
        indexes = [
            models.Index(fields=["job", "created_at"]),
            models.Index(fields=["to_status", "created_at"]),
        ]


class AuditEvent(models.Model):
    """Tenant-scoped audit events for inference operations."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="audit_events",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inference_audit_events",
    )
    job = models.ForeignKey(
        InferenceJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=64)
    correlation_id = models.CharField(max_length=255, null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inference_audit_event"
        indexes = [
            models.Index(fields=["tenant", "timestamp"]),
            models.Index(fields=["job", "timestamp"]),
            models.Index(fields=["action", "timestamp"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} ({self.tenant_id})"
