from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import BinaryIO

from settings import settings
from services.job_store import create_or_get_job_record, get_job, mark_job_failed
from services.sqs import enqueue_job
from services.storage import (
    build_job_artifacts,
    generate_presigned_get_url,
    object_exists,
    parse_s3_uri,
    upload_fileobj,
)

logger = logging.getLogger(__name__)


def _stable_job_id(idempotency_key: str | None) -> str:
    if not idempotency_key:
        return str(uuid.uuid4())
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return str(uuid.UUID(digest[:32]))


def _normalize_requested_device(requested_device: str | None) -> str:
    value = (requested_device or settings.DEFAULT_REQUESTED_DEVICE).strip().lower()
    if value not in {"cuda", "cpu", "auto"}:
        raise ValueError("requested_device must be one of: cuda, cpu, auto")
    return value


def _normalize_slice_batch_size(slice_batch_size: int | None) -> int | None:
    if slice_batch_size is None:
        return settings.DEFAULT_SLICE_BATCH_SIZE
    if slice_batch_size <= 0:
        raise ValueError("slice_batch_size must be greater than zero")
    return slice_batch_size


def _build_queue_payload(job: dict) -> dict:
    payload = {
        "job_id": job["job_id"],
        "input_s3_uri": job["input_s3_uri"],
        "output_s3_uri": job["output_s3_uri"],
        "summary_s3_uri": job["summary_s3_uri"],
        "requested_device": job["requested_device"],
        "request_id": job["request_id"],
        "correlation_id": job["correlation_id"],
    }
    if job.get("slice_batch_size") is not None:
        payload["slice_batch_size"] = job["slice_batch_size"]
    return payload


def serialize_job(job: dict) -> dict:
    response = {
        "job_id": job["job_id"],
        "status": job["status"],
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "requested_device": job.get("requested_device"),
        "slice_batch_size": job.get("slice_batch_size"),
        "attempt_count": job.get("attempt_count", 0),
        "request_id": job.get("request_id"),
        "correlation_id": job.get("correlation_id"),
        "error_message": job.get("error_message"),
        "error_type": job.get("error_type"),
        "result": {
            "input_s3_uri": job.get("input_s3_uri"),
            "output_s3_uri": job.get("output_s3_uri"),
            "summary_s3_uri": job.get("summary_s3_uri"),
        },
    }

    if job.get("status") == "succeeded":
        for field_name in ("output_s3_uri", "summary_s3_uri"):
            uri = job.get(field_name)
            if not uri:
                continue
            bucket, key = parse_s3_uri(uri)
            if object_exists(bucket, key):
                response["result"][field_name.replace("_s3_uri", "_download_url")] = (
                    generate_presigned_get_url(bucket, key)
                )

    return response


def get_job_details(job_id: str) -> dict | None:
    job = get_job(job_id)
    if not job:
        return None
    return serialize_job(job)


def create_job_from_upload(
    *,
    fileobj: BinaryIO,
    requested_device: str | None,
    slice_batch_size: int | None,
    request_id: str,
    correlation_id: str,
    idempotency_key: str | None,
) -> dict:
    job_id = _stable_job_id(idempotency_key)
    existing = get_job(job_id)
    if existing is not None:
        logger.info(
            json.dumps(
                {
                    "event": "job_reused",
                    "job_id": job_id,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                }
            )
        )
        return serialize_job(existing)

    requested_device = _normalize_requested_device(requested_device)
    slice_batch_size = _normalize_slice_batch_size(slice_batch_size)
    artifacts = build_job_artifacts(job_id)

    upload_fileobj(
        fileobj=fileobj,
        bucket=settings.ARTIFACTS_BUCKET,
        key=artifacts["input_key"],
        content_type="application/octet-stream",
    )

    job, created = create_or_get_job_record(
        job_id=job_id,
        input_s3_uri=artifacts["input_s3_uri"],
        output_s3_uri=artifacts["output_s3_uri"],
        summary_s3_uri=artifacts["summary_s3_uri"],
        requested_device=requested_device,
        slice_batch_size=slice_batch_size,
        request_id=request_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        source="upload",
    )
    if not created:
        return serialize_job(job)

    try:
        enqueue_job(_build_queue_payload(job))
    except Exception as exc:
        mark_job_failed(job_id, str(exc), type(exc).__name__)
        logger.exception("failed to enqueue job")
        raise

    logger.info(
        json.dumps(
            {
                "event": "job_created",
                "job_id": job_id,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "input_s3_uri": artifacts["input_s3_uri"],
                "output_s3_uri": artifacts["output_s3_uri"],
                "summary_s3_uri": artifacts["summary_s3_uri"],
                "requested_device": requested_device,
                "slice_batch_size": slice_batch_size,
            }
        )
    )
    return serialize_job(job)


def create_job_from_reference(
    *,
    input_s3_uri: str,
    requested_device: str | None,
    slice_batch_size: int | None,
    request_id: str,
    correlation_id: str,
    idempotency_key: str | None,
) -> dict:
    bucket, key = parse_s3_uri(input_s3_uri)
    if bucket != settings.ARTIFACTS_BUCKET:
        raise ValueError("Referenced inputs must already be in the configured artifacts bucket")
    if not key.endswith(".npz"):
        raise ValueError("Referenced input must point to a .npz object")
    if not object_exists(bucket, key):
        raise ValueError("Referenced input object was not found")

    job_id = _stable_job_id(idempotency_key)
    existing = get_job(job_id)
    if existing is not None:
        return serialize_job(existing)

    requested_device = _normalize_requested_device(requested_device)
    slice_batch_size = _normalize_slice_batch_size(slice_batch_size)
    artifacts = build_job_artifacts(job_id)

    job, created = create_or_get_job_record(
        job_id=job_id,
        input_s3_uri=input_s3_uri,
        output_s3_uri=artifacts["output_s3_uri"],
        summary_s3_uri=artifacts["summary_s3_uri"],
        requested_device=requested_device,
        slice_batch_size=slice_batch_size,
        request_id=request_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        source="reference",
    )
    if not created:
        return serialize_job(job)

    try:
        enqueue_job(_build_queue_payload(job))
    except Exception as exc:
        mark_job_failed(job_id, str(exc), type(exc).__name__)
        logger.exception("failed to enqueue referenced job")
        raise

    return serialize_job(job)
