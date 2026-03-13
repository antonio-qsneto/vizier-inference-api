"""Idempotent state machine for inference jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from .models import InferenceJob, JobStatusHistory


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    InferenceJob.STATUS_CREATED: {
        InferenceJob.STATUS_UPLOAD_PENDING,
        InferenceJob.STATUS_FAILED,
    },
    InferenceJob.STATUS_UPLOAD_PENDING: {
        InferenceJob.STATUS_UPLOADED,
        InferenceJob.STATUS_FAILED,
    },
    InferenceJob.STATUS_UPLOADED: {
        InferenceJob.STATUS_VALIDATING,
        InferenceJob.STATUS_QUEUED,
        InferenceJob.STATUS_FAILED,
    },
    InferenceJob.STATUS_VALIDATING: {
        InferenceJob.STATUS_PREPROCESSING,
        InferenceJob.STATUS_RUNNING,
        InferenceJob.STATUS_FAILED,
    },
    InferenceJob.STATUS_PREPROCESSING: {
        InferenceJob.STATUS_RUNNING,
        InferenceJob.STATUS_FAILED,
    },
    InferenceJob.STATUS_QUEUED: {
        InferenceJob.STATUS_VALIDATING,
        InferenceJob.STATUS_RUNNING,
        InferenceJob.STATUS_FAILED,
    },
    InferenceJob.STATUS_RUNNING: {
        InferenceJob.STATUS_POSTPROCESSING,
        InferenceJob.STATUS_COMPLETED,
        InferenceJob.STATUS_FAILED,
    },
    InferenceJob.STATUS_POSTPROCESSING: {
        InferenceJob.STATUS_COMPLETED,
        InferenceJob.STATUS_FAILED,
    },
    InferenceJob.STATUS_COMPLETED: set(),
    InferenceJob.STATUS_FAILED: set(),
}


@dataclass
class TransitionResult:
    job: InferenceJob
    changed: bool
    reason: str


@transaction.atomic
def transition_job(
    *,
    job: InferenceJob,
    to_status: str,
    actor_user=None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
    progress_percent: int | None = None,
    allow_noop: bool = True,
) -> TransitionResult:
    """Transition job status with idempotent semantics."""
    metadata = metadata or {}
    current_status = job.status

    if current_status == to_status:
        if allow_noop:
            return TransitionResult(job=job, changed=False, reason="noop_same_state")
        raise ValueError(f"Job {job.id} is already in state {to_status}")

    if current_status in InferenceJob.TERMINAL_STATUSES:
        if allow_noop:
            return TransitionResult(job=job, changed=False, reason="noop_terminal")
        raise ValueError(f"Cannot transition terminal job {job.id} from {current_status} to {to_status}")

    allowed_next = ALLOWED_TRANSITIONS.get(current_status, set())
    if to_status not in allowed_next:
        if allow_noop:
            return TransitionResult(job=job, changed=False, reason="noop_invalid_transition")
        raise ValueError(f"Invalid transition: {current_status} -> {to_status}")

    job.status = to_status
    if progress_percent is not None:
        job.progress_percent = max(0, min(100, int(progress_percent)))

    if to_status == InferenceJob.STATUS_UPLOADED and not job.uploaded_at:
        job.uploaded_at = timezone.now()

    if to_status == InferenceJob.STATUS_RUNNING and not job.started_at:
        job.started_at = timezone.now()

    if to_status in InferenceJob.TERMINAL_STATUSES:
        job.completed_at = timezone.now()

    if to_status != InferenceJob.STATUS_FAILED:
        job.error_type = None
        job.error_message = None

    job.save(
        update_fields=[
            "status",
            "progress_percent",
            "uploaded_at",
            "started_at",
            "completed_at",
            "error_type",
            "error_message",
            "updated_at",
        ]
    )

    JobStatusHistory.objects.create(
        job=job,
        from_status=current_status,
        to_status=to_status,
        actor_user=actor_user,
        reason=(reason or "").strip() or None,
        metadata=metadata,
    )

    return TransitionResult(job=job, changed=True, reason="changed")


@transaction.atomic
def mark_job_failed(
    *,
    job: InferenceJob,
    error_type: str,
    error_message: str,
    actor_user=None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TransitionResult:
    metadata = metadata or {}

    if job.status in InferenceJob.TERMINAL_STATUSES:
        return TransitionResult(job=job, changed=False, reason="noop_terminal")

    current = job.status
    job.status = InferenceJob.STATUS_FAILED
    job.error_type = (error_type or "RuntimeError")[:128]
    job.error_message = (error_message or "Unknown failure")[:4000]
    job.completed_at = timezone.now()
    job.save(
        update_fields=[
            "status",
            "error_type",
            "error_message",
            "completed_at",
            "updated_at",
        ]
    )

    JobStatusHistory.objects.create(
        job=job,
        from_status=current,
        to_status=InferenceJob.STATUS_FAILED,
        actor_user=actor_user,
        reason=(reason or "")[:255] or None,
        metadata=metadata,
    )

    return TransitionResult(job=job, changed=True, reason="changed")
