"""Control-plane API for async S3-first inference jobs."""

from __future__ import annotations

import json
import logging
import uuid

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.rbac import RBACPermission, has_scoped_permission
from services.presign_service import PresignService
from services.queue_service import QueueService
from services.s3_utils import S3Utils

from .models import AuditEvent, InferenceJob, InputArtifact, JobStatusHistory, ModelVersion, OutputArtifact, Tenant
from .object_layout import raw_input_key
from .prompt_catalog import build_text_prompts_for_job
from .serializers import (
    InferenceJobCreateRequestSerializer,
    InferenceJobCreateResponseSerializer,
    InferenceJobListResponseSerializer,
    InferenceJobOutputsResponseSerializer,
    InferenceJobStatusSerializer,
    InputArtifactUploadCompleteSerializer,
    OutputPresignDownloadResponseSerializer,
)
from .state_machine import mark_job_failed, transition_job

logger = logging.getLogger(__name__)


def _request_id(request) -> str:
    return str(
        request.headers.get("X-Request-ID")
        or request.META.get("HTTP_X_REQUEST_ID")
        or uuid.uuid4()
    )


def _user_can_create_jobs(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False

    if not user.has_upload_access():
        return False

    if getattr(user, "clinic_id", None):
        return has_scoped_permission(
            user,
            RBACPermission.STUDIES_CREATE,
            tenant_id=user.clinic_id,
        )

    return has_scoped_permission(
        user,
        RBACPermission.STUDIES_CREATE,
        resource_owner_user_id=user.id,
    )


def _job_accessible_by_user(job: InferenceJob, user) -> bool:
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True

    if getattr(user, "clinic_id", None):
        return bool(job.tenant.clinic_id and str(job.tenant.clinic_id) == str(user.clinic_id))

    return str(job.owner_id) == str(user.id)


def _resolve_or_create_model_version(serializer: InferenceJobCreateRequestSerializer) -> ModelVersion:
    requested_name = str(serializer.validated_data.get("requested_model") or "biomedparse").strip() or "biomedparse"
    requested_version = str(serializer.validated_data.get("requested_model_version") or "v1").strip() or "v1"

    model_version, _ = ModelVersion.objects.get_or_create(
        name=requested_name,
        version=requested_version,
        defaults={
            "executor": "biomedparse",
            "is_active": True,
            "metadata": {},
        },
    )
    return model_version


def _build_upload_instructions(*, artifact: InputArtifact, job: InferenceJob) -> dict:
    presign = PresignService()
    instructions = presign.create_upload_post(
        key=artifact.key,
        content_type=artifact.content_type or "application/octet-stream",
        tenant_id=str(job.tenant_id),
        job_id=str(job.id),
    )
    return {
        "method": instructions.method,
        "url": instructions.url,
        "fields": instructions.fields,
        "key": instructions.key,
        "expires_in": instructions.expires_in,
        "bucket": artifact.bucket,
        "input_artifact_id": str(artifact.id),
    }


def _emit_audit_event(*, job: InferenceJob, action: str, user=None, payload: dict | None = None) -> None:
    AuditEvent.objects.create(
        tenant=job.tenant,
        user=user,
        job=job,
        action=action,
        correlation_id=job.correlation_id,
        payload=payload or {},
    )


class InferenceJobCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not getattr(settings, "INFERENCE_ASYNC_S3_ENABLED", False):
            return Response(
                {"detail": "Async inference API is disabled"},
                status=status.HTTP_404_NOT_FOUND,
            )

        jobs_qs = InferenceJob.objects.select_related("tenant", "owner").order_by("-created_at")
        if not (getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)):
            if getattr(request.user, "clinic_id", None):
                jobs_qs = jobs_qs.filter(tenant__clinic_id=request.user.clinic_id)
            else:
                jobs_qs = jobs_qs.filter(owner=request.user)

        requested_status = str(request.query_params.get("status") or "").strip().upper()
        if requested_status:
            jobs_qs = jobs_qs.filter(status=requested_status)

        try:
            limit = int(request.query_params.get("limit", 200))
        except (TypeError, ValueError):
            limit = 200
        limit = max(1, min(limit, 500))

        jobs = list(jobs_qs[:limit])
        serializer = InferenceJobListResponseSerializer(
            {
                "count": len(jobs),
                "results": jobs,
            }
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        if not getattr(settings, "INFERENCE_ASYNC_S3_ENABLED", False):
            return Response(
                {"detail": "Async inference API is disabled"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not _user_can_create_jobs(request.user):
            return Response(
                {"detail": "Permission denied to create inference jobs in this scope"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = InferenceJobCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant = Tenant.resolve_for_user(request.user)
        idempotency_key = (
            request.headers.get("Idempotency-Key")
            or request.META.get("HTTP_IDEMPOTENCY_KEY")
            or None
        )
        correlation_id = str(serializer.validated_data.get("correlation_id") or _request_id(request))

        if idempotency_key:
            existing = (
                InferenceJob.objects.filter(
                    tenant=tenant,
                    idempotency_key=idempotency_key,
                )
                .select_related("tenant")
                .prefetch_related("input_artifacts")
                .first()
            )
            if existing:
                artifact = existing.input_artifacts.filter(kind=InputArtifact.KIND_RAW_UPLOAD).first()
                upload = (
                    _build_upload_instructions(artifact=artifact, job=existing)
                    if artifact and existing.status in {InferenceJob.STATUS_UPLOAD_PENDING, InferenceJob.STATUS_CREATED}
                    else {}
                )
                response_serializer = InferenceJobCreateResponseSerializer(
                    {
                        "job_id": existing.id,
                        "status": existing.status,
                        "tenant_id": existing.tenant_id,
                        "correlation_id": existing.correlation_id,
                        "upload": upload,
                    }
                )
                return Response(response_serializer.data, status=status.HTTP_200_OK)

        model_version = _resolve_or_create_model_version(serializer)

        file_name = serializer.validated_data["file_name"]
        content_type = serializer.validated_data.get("content_type") or "application/octet-stream"
        exam_modality = serializer.validated_data.get("exam_modality")
        category_id = serializer.validated_data.get("category_id")
        text_prompts = build_text_prompts_for_job(
            exam_modality=exam_modality,
            category_id=category_id,
        )

        with transaction.atomic():
            job = InferenceJob.objects.create(
                tenant=tenant,
                owner=request.user,
                requested_model_version=model_version,
                status=InferenceJob.STATUS_CREATED,
                requested_device=serializer.validated_data.get("requested_device") or "cuda",
                slice_batch_size=serializer.validated_data.get("slice_batch_size"),
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                request_payload={
                    "file_name": file_name,
                    "file_size": serializer.validated_data.get("file_size"),
                    "content_type": content_type,
                    "case_identification": serializer.validated_data.get("case_identification"),
                    "patient_name": serializer.validated_data.get("patient_name"),
                    "age": serializer.validated_data.get("age"),
                    "exam_source": serializer.validated_data.get("exam_source"),
                    "exam_modality": exam_modality,
                    "category_id": category_id,
                    "requested_device": serializer.validated_data.get("requested_device") or "cuda",
                    "slice_batch_size": serializer.validated_data.get("slice_batch_size"),
                    "text_prompts": text_prompts,
                },
            )
            JobStatusHistory.objects.create(
                job=job,
                from_status=None,
                to_status=InferenceJob.STATUS_CREATED,
                actor_user=request.user,
                reason="job_created",
                metadata={},
            )
            transition_job(
                job=job,
                to_status=InferenceJob.STATUS_UPLOAD_PENDING,
                actor_user=request.user,
                reason="awaiting_client_upload",
                metadata={},
            )

            key = raw_input_key(str(tenant.id), str(job.id), file_name)
            artifact = InputArtifact.objects.create(
                job=job,
                bucket=settings.S3_BUCKET,
                key=key,
                kind=InputArtifact.KIND_RAW_UPLOAD,
                original_filename=file_name,
                content_type=content_type,
                size_bytes=serializer.validated_data.get("file_size"),
                upload_status=InputArtifact.STATUS_PENDING,
                metadata={
                    "tenant_id": str(tenant.id),
                    "job_id": str(job.id),
                },
            )

        upload = _build_upload_instructions(artifact=artifact, job=job)
        _emit_audit_event(
            job=job,
            action="INFERENCE_JOB_CREATED",
            user=request.user,
            payload={"input_key": artifact.key, "idempotency_key": idempotency_key},
        )

        logger.info(
            json.dumps(
                {
                    "event": "inference_job_created",
                    "job_id": str(job.id),
                    "tenant_id": str(job.tenant_id),
                    "owner_id": request.user.id,
                    "correlation_id": job.correlation_id,
                    "input_key": artifact.key,
                }
            )
        )

        response_serializer = InferenceJobCreateResponseSerializer(
            {
                "job_id": job.id,
                "status": job.status,
                "tenant_id": job.tenant_id,
                "correlation_id": job.correlation_id,
                "upload": upload,
            }
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class InferenceJobUploadCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, job_id: str):
        if not getattr(settings, "INFERENCE_ASYNC_S3_ENABLED", False):
            return Response({"detail": "Async inference API is disabled"}, status=status.HTTP_404_NOT_FOUND)

        serializer = InputArtifactUploadCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        job = get_object_or_404(
            InferenceJob.objects.select_related("tenant", "owner").prefetch_related("input_artifacts"),
            id=job_id,
        )
        if not _job_accessible_by_user(job, request.user):
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        if job.is_terminal:
            return Response(InferenceJobStatusSerializer(job).data, status=status.HTTP_200_OK)

        if job.status in {
            InferenceJob.STATUS_QUEUED,
            InferenceJob.STATUS_RUNNING,
            InferenceJob.STATUS_POSTPROCESSING,
        }:
            # Idempotent retry: job already accepted by worker path.
            return Response(InferenceJobStatusSerializer(job).data, status=status.HTTP_200_OK)

        artifact = None
        artifact_id = serializer.validated_data.get("input_artifact_id")
        key = serializer.validated_data.get("key")
        if artifact_id:
            artifact = job.input_artifacts.filter(id=artifact_id).first()
        elif key:
            artifact = job.input_artifacts.filter(key=key).first()
        else:
            artifact = job.input_artifacts.filter(kind=InputArtifact.KIND_RAW_UPLOAD).first()

        if not artifact:
            return Response({"detail": "Input artifact not found for this job"}, status=status.HTTP_400_BAD_REQUEST)

        s3 = S3Utils()
        head = s3.head_object(artifact.key)
        if not head:
            return Response({"detail": "Uploaded object not found in S3"}, status=status.HTTP_400_BAD_REQUEST)

        actual_size = int(head.get("ContentLength") or 0)
        provided_size = serializer.validated_data.get("size_bytes")
        if provided_size and int(provided_size) != actual_size:
            return Response(
                {
                    "detail": "Uploaded object size mismatch",
                    "expected": int(provided_size),
                    "actual": actual_size,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        artifact.size_bytes = actual_size
        artifact.etag = (
            serializer.validated_data.get("etag")
            or str(head.get("ETag") or "").replace('"', "")
            or artifact.etag
        )
        artifact.upload_status = InputArtifact.STATUS_UPLOADED
        artifact.save(update_fields=["size_bytes", "etag", "upload_status", "updated_at"])

        transition_job(
            job=job,
            to_status=InferenceJob.STATUS_UPLOADED,
            actor_user=request.user,
            reason="client_upload_completed",
            metadata={"input_artifact_id": str(artifact.id)},
        )

        if job.status != InferenceJob.STATUS_UPLOADED:
            return Response(InferenceJobStatusSerializer(job).data, status=status.HTTP_200_OK)

        requested_model_version = (
            f"{job.requested_model_version.name}-{job.requested_model_version.version}"
            if job.requested_model_version
            else "biomedparse-v1"
        )
        requested_device = (job.requested_device or "cuda").strip().lower() or "cuda"
        slice_batch_size = job.slice_batch_size

        queue_payload = {
            "schema_version": 2,
            "event_type": "inference.job.uploaded",
            "job_id": str(job.id),
            "tenant_id": str(job.tenant_id),
            "input_artifact_id": str(artifact.id),
            "input_bucket": artifact.bucket,
            "input_key": artifact.key,
            "correlation_id": job.correlation_id,
            "requested_by_user_id": job.owner_id,
            "requested_model_version": requested_model_version,
            "requested_device": requested_device,
            "slice_batch_size": slice_batch_size,
            "requested_at": job.created_at.isoformat(),
        }

        try:
            QueueService().enqueue_job(queue_payload)
        except Exception as exc:
            mark_job_failed(
                job=job,
                error_type=type(exc).__name__,
                error_message=str(exc),
                actor_user=request.user,
                reason="failed_to_enqueue",
                metadata={"queue_payload": queue_payload},
            )
            logger.exception("Failed to enqueue inference job", extra={"job_id": str(job.id)})
            return Response(
                {"detail": "Failed to enqueue processing job", "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        transition_job(
            job=job,
            to_status=InferenceJob.STATUS_QUEUED,
            actor_user=request.user,
            reason="published_to_sqs",
            metadata={"queue_payload": queue_payload},
            progress_percent=5,
        )

        _emit_audit_event(
            job=job,
            action="INFERENCE_JOB_QUEUED",
            user=request.user,
            payload={"input_artifact_id": str(artifact.id), "queue_payload": queue_payload},
        )

        logger.info(
            json.dumps(
                {
                    "event": "inference_job_queued",
                    "job_id": str(job.id),
                    "tenant_id": str(job.tenant_id),
                    "correlation_id": job.correlation_id,
                    "input_key": artifact.key,
                }
            )
        )

        return Response(InferenceJobStatusSerializer(job).data, status=status.HTTP_200_OK)


class InferenceJobStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id: str):
        if not getattr(settings, "INFERENCE_ASYNC_S3_ENABLED", False):
            return Response({"detail": "Async inference API is disabled"}, status=status.HTTP_404_NOT_FOUND)

        job = get_object_or_404(
            InferenceJob.objects.select_related("tenant", "owner").prefetch_related("input_artifacts"),
            id=job_id,
        )
        if not _job_accessible_by_user(job, request.user):
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        return Response(InferenceJobStatusSerializer(job).data)


class InferenceJobOutputsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id: str):
        if not getattr(settings, "INFERENCE_ASYNC_S3_ENABLED", False):
            return Response({"detail": "Async inference API is disabled"}, status=status.HTTP_404_NOT_FOUND)

        job = get_object_or_404(
            InferenceJob.objects.select_related("tenant", "owner").prefetch_related("output_artifacts"),
            id=job_id,
        )
        if not _job_accessible_by_user(job, request.user):
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        outputs = job.output_artifacts.order_by("kind", "created_at")
        serializer = InferenceJobOutputsResponseSerializer(
            {
                "job_id": job.id,
                "status": job.status,
                "outputs": outputs,
            }
        )
        return Response(serializer.data)


class InferenceOutputPresignDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, job_id: str, output_id: str):
        if not getattr(settings, "INFERENCE_ASYNC_S3_ENABLED", False):
            return Response({"detail": "Async inference API is disabled"}, status=status.HTTP_404_NOT_FOUND)

        job = get_object_or_404(InferenceJob.objects.select_related("tenant", "owner"), id=job_id)
        if not _job_accessible_by_user(job, request.user):
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        output = get_object_or_404(OutputArtifact.objects.filter(job=job), id=output_id)

        presign = PresignService()
        url, expires_in = presign.create_download_url(key=output.key)
        serializer = OutputPresignDownloadResponseSerializer(
            {
                "output_id": output.id,
                "kind": output.kind,
                "url": url,
                "expires_in": expires_in,
            }
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
