import uuid

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from services.jobs import create_job_from_upload

router = APIRouter()


@router.post("/submit")
async def submit_job(
    file: UploadFile = File(...),
    requested_device: str | None = Form(default=None),
    slice_batch_size: int | None = Form(default=None),
    request_id: str | None = Form(default=None),
    correlation_id: str | None = Form(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
):
    if not (file.filename or "").lower().endswith(".npz"):
        raise HTTPException(status_code=400, detail="Only .npz files are accepted")

    resolved_request_id = request_id or x_request_id or str(uuid.uuid4())
    try:
        job = create_job_from_upload(
            fileobj=file.file,
            requested_device=requested_device,
            slice_batch_size=slice_batch_size,
            request_id=resolved_request_id,
            correlation_id=correlation_id or resolved_request_id,
            idempotency_key=idempotency_key,
        )
        return job
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
