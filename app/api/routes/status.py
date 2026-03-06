from fastapi import APIRouter, HTTPException

from services.jobs import get_job_details

router = APIRouter()


@router.get("/{job_id}/status")
def job_status(job_id: str):
    job = get_job_details(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "attempt_count": job.get("attempt_count", 0),
        "requested_device": job.get("requested_device"),
        "slice_batch_size": job.get("slice_batch_size"),
        "error_message": job.get("error_message"),
        "error_type": job.get("error_type"),
        "request_id": job.get("request_id"),
        "correlation_id": job.get("correlation_id"),
    }
