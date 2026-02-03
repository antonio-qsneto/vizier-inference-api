# app/api/routes/status.py
from fastapi import APIRouter, HTTPException
from pathlib import Path
from settings import settings

router = APIRouter()

@router.get("/{job_id}/status")
def job_status(job_id: str):
    status_file = Path(settings.JOB_BASE_DIR) / job_id / "status.txt"

    if not status_file.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    return {"job_id": job_id, "status": status_file.read_text()}
