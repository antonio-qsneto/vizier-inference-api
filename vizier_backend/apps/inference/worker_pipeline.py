"""Worker pipeline for async S3-first inference jobs."""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Callable

from django.conf import settings
from django.db import transaction

from services.s3_utils import S3Utils
from services.nifti_converter import NiftiConverter

from .executors.biomedparse_ecs_executor import BiomedParseECSExecutor
from .executors.preprocessing_executor import InferencePreprocessor
from .models import AuditEvent, InferenceJob, InputArtifact, OutputArtifact
from .object_layout import (
    audit_processing_metadata_key,
    normalized_input_key,
    output_mask_npz_key,
    output_mask_nifti_key,
    output_original_nifti_key,
    output_summary_key,
)
from .state_machine import mark_job_failed, transition_job

logger = logging.getLogger(__name__)


class InferenceWorkerPipeline:
    def __init__(self):
        self.s3 = S3Utils()
        self.preprocessor = InferencePreprocessor()
        self.executor = BiomedParseECSExecutor()

    def process_message(
        self,
        payload: dict,
        *,
        visibility_heartbeat: Callable[[], None] | None = None,
    ) -> None:
        job_id = payload.get("job_id")
        if not job_id:
            raise ValueError("Missing job_id in queue payload")

        job = (
            InferenceJob.objects.select_related("tenant", "owner", "requested_model_version")
            .prefetch_related("input_artifacts", "output_artifacts")
            .get(id=job_id)
        )

        if job.is_terminal:
            logger.info(
                json.dumps(
                    {
                        "event": "worker_job_already_terminal",
                        "job_id": str(job.id),
                        "status": job.status,
                    }
                )
            )
            return

        if job.status not in {
            InferenceJob.STATUS_QUEUED,
            InferenceJob.STATUS_UPLOADED,
        }:
            logger.info(
                json.dumps(
                    {
                        "event": "worker_job_skipped_unexpected_status",
                        "job_id": str(job.id),
                        "status": job.status,
                    }
                )
            )
            return

        input_artifact_id = payload.get("input_artifact_id")
        input_artifact = None
        if input_artifact_id:
            input_artifact = job.input_artifacts.filter(id=input_artifact_id).first()

        if not input_artifact:
            input_artifact = job.input_artifacts.filter(kind=InputArtifact.KIND_RAW_UPLOAD).first()

        if not input_artifact:
            raise RuntimeError(f"Job {job.id} has no input artifact")

        tenant_id = str(job.tenant_id)
        job_id_text = str(job.id)
        normalized_key = normalized_input_key(tenant_id, job_id_text)
        original_nifti_key = output_original_nifti_key(tenant_id, job_id_text)
        mask_nifti_key = output_mask_nifti_key(tenant_id, job_id_text)
        summary_key = output_summary_key(tenant_id, job_id_text)

        # Reconcile idempotently if all final artifacts already exist.
        if (
            self.s3.object_exists(original_nifti_key)
            and self.s3.object_exists(mask_nifti_key)
            and self.s3.object_exists(summary_key)
        ):
            transition_job(
                job=job,
                to_status=InferenceJob.STATUS_COMPLETED,
                reason="worker_reconciled_existing_outputs",
                metadata={},
                progress_percent=100,
            )
            logger.info(
                json.dumps(
                    {
                        "event": "worker_job_reconciled",
                        "job_id": job_id_text,
                        "tenant_id": tenant_id,
                    }
                )
            )
            return

        scratch_root = Path(f"/tmp/jobs/{job.id}")
        scratch_root.mkdir(parents=True, exist_ok=True)

        local_input_path = scratch_root / (Path(input_artifact.key).name or "input.bin")
        if not self.s3.download_file(input_artifact.key, str(local_input_path)):
            raise RuntimeError(f"Failed to download input artifact s3://{input_artifact.bucket}/{input_artifact.key}")

        try:
            transition_job(
                job=job,
                to_status=InferenceJob.STATUS_VALIDATING,
                reason="worker_validating_input",
                metadata={"input_key": input_artifact.key},
                progress_percent=10,
            )
            input_artifact.upload_status = InputArtifact.STATUS_VALIDATED
            input_artifact.save(update_fields=["upload_status", "updated_at"])

            transition_job(
                job=job,
                to_status=InferenceJob.STATUS_PREPROCESSING,
                reason="worker_preprocessing",
                metadata={},
                progress_percent=20,
            )

            prepared = self.preprocessor.prepare_input(
                input_file_path=str(local_input_path),
                work_dir=str(scratch_root),
                text_prompts={},
                exam_modality=(job.request_payload or {}).get("exam_modality"),
                category_hint=(job.request_payload or {}).get("category_id"),
            )
            normalized_npz_local = prepared["normalized_input_npz"]
            original_nifti_local = prepared["original_nifti"]

            if not self.s3.upload_file(normalized_npz_local, normalized_key, "application/octet-stream"):
                raise RuntimeError(f"Failed to upload normalized input key={normalized_key}")

            transition_job(
                job=job,
                to_status=InferenceJob.STATUS_RUNNING,
                reason="worker_running_executor",
                metadata={},
                progress_percent=40,
            )

            job.attempt_count = int(job.attempt_count or 0) + 1
            job.save(update_fields=["attempt_count", "updated_at"])

            outputs = self.executor.run(
                job_id=job_id_text,
                normalized_input_key=normalized_key,
                work_dir=str(scratch_root),
                requested_device=(payload.get("requested_device") or job.requested_device or "cuda"),
                slice_batch_size=(
                    payload.get("slice_batch_size")
                    if payload.get("slice_batch_size") is not None
                    else job.slice_batch_size
                ),
                tenant_id=tenant_id,
                on_poll=visibility_heartbeat,
            )
            job.gpu_task_arn = outputs.get("gpu_task_arn")
            job.save(update_fields=["gpu_task_arn", "updated_at"])

            transition_job(
                job=job,
                to_status=InferenceJob.STATUS_POSTPROCESSING,
                reason="worker_uploading_outputs",
                metadata={"gpu_task_arn": outputs.get("gpu_task_arn")},
                progress_percent=80,
            )

            mask_npz_local = outputs["mask_npz_local"]
            summary_local = outputs["summary_json_local"]
            mask_nifti_local = os.path.join(str(scratch_root), "mask.nii.gz")
            if not NiftiConverter.segs_npz_to_nifti(mask_npz_local, mask_nifti_local):
                raise RuntimeError("Failed to convert mask NPZ to NIfTI")
            if not NiftiConverter.align_mask_to_reference(
                mask_nifti_path=mask_nifti_local,
                reference_nifti_path=original_nifti_local,
                output_path=mask_nifti_local,
            ):
                raise RuntimeError("Failed to align mask NIfTI to original image dimensions")

            output_specs = [
                (
                    OutputArtifact.KIND_NORMALIZED_INPUT_NPZ,
                    normalized_npz_local,
                    normalized_key,
                    "application/octet-stream",
                ),
                (
                    OutputArtifact.KIND_ORIGINAL_NIFTI,
                    original_nifti_local,
                    original_nifti_key,
                    "application/gzip",
                ),
                (
                    OutputArtifact.KIND_MASK_NIFTI,
                    mask_nifti_local,
                    mask_nifti_key,
                    "application/gzip",
                ),
                (
                    OutputArtifact.KIND_SUMMARY_JSON,
                    summary_local,
                    summary_key,
                    "application/json",
                ),
            ]

            with transaction.atomic():
                for kind, local_path, key, content_type in output_specs:
                    if not self.s3.upload_file(local_path, key, content_type):
                        raise RuntimeError(f"Failed to upload artifact kind={kind} to key={key}")

                    head = self.s3.head_object(key) or {}
                    OutputArtifact.objects.update_or_create(
                        job=job,
                        kind=kind,
                        defaults={
                            "bucket": settings.S3_BUCKET,
                            "key": key,
                            "content_type": content_type,
                            "size_bytes": int(head.get("ContentLength") or os.path.getsize(local_path)),
                            "etag": str(head.get("ETag") or "").replace('"', "") or None,
                            "metadata": {
                                "tenant_id": tenant_id,
                                "job_id": job_id_text,
                                "correlation_id": job.correlation_id,
                                "gpu_task_arn": outputs.get("gpu_task_arn"),
                            },
                        },
                    )

                processing_metadata = {
                    "job_id": job_id_text,
                    "tenant_id": tenant_id,
                    "correlation_id": job.correlation_id,
                    "gpu_task_arn": outputs.get("gpu_task_arn"),
                    "input_key": input_artifact.key,
                    "output_keys": {
                        "normalized_input": normalized_key,
                        "mask_npz_raw": output_mask_npz_key(tenant_id, job_id_text),
                        "original_nifti": original_nifti_key,
                        "mask_nifti": mask_nifti_key,
                        "summary": summary_key,
                    },
                }
                metadata_key = audit_processing_metadata_key(tenant_id, job_id_text)
                self.s3.upload_bytes(
                    json.dumps(processing_metadata, ensure_ascii=True, indent=2).encode("utf-8"),
                    metadata_key,
                    "application/json",
                )

            transition_job(
                job=job,
                to_status=InferenceJob.STATUS_COMPLETED,
                reason="worker_completed",
                metadata={"gpu_task_arn": outputs.get("gpu_task_arn")},
                progress_percent=100,
            )

            AuditEvent.objects.create(
                tenant=job.tenant,
                user=job.owner,
                job=job,
                action="INFERENCE_JOB_COMPLETED",
                correlation_id=job.correlation_id,
                payload={
                    "gpu_task_arn": outputs.get("gpu_task_arn"),
                    "input_key": input_artifact.key,
                },
            )

            logger.info(
                json.dumps(
                    {
                        "event": "worker_job_completed",
                        "job_id": str(job.id),
                        "tenant_id": str(job.tenant_id),
                        "correlation_id": job.correlation_id,
                    }
                )
            )

        except Exception as exc:
            mark_job_failed(
                job=job,
                error_type=type(exc).__name__,
                error_message=str(exc),
                reason="worker_failed",
                metadata={"input_key": input_artifact.key},
            )
            AuditEvent.objects.create(
                tenant=job.tenant,
                user=job.owner,
                job=job,
                action="INFERENCE_JOB_FAILED",
                correlation_id=job.correlation_id,
                payload={
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            raise
        finally:
            if scratch_root.exists():
                shutil.rmtree(scratch_root, ignore_errors=True)
