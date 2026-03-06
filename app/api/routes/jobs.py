import uuid

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from services.jobs import create_job_from_reference, get_job_details

router = APIRouter()


class ReferenceJobRequest(BaseModel):
    input_s3_uri: str
    requested_device: str | None = None
    slice_batch_size: int | None = None
    request_id: str | None = None
    correlation_id: str | None = None


@router.post("")
def create_job(
    payload: ReferenceJobRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
):
    resolved_request_id = payload.request_id or x_request_id or str(uuid.uuid4())
    try:
        return create_job_from_reference(
            input_s3_uri=payload.input_s3_uri,
            requested_device=payload.requested_device,
            slice_batch_size=payload.slice_batch_size,
            request_id=resolved_request_id,
            correlation_id=payload.correlation_id or resolved_request_id,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{job_id}")
def get_job(job_id: str):
    job = get_job_details(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
