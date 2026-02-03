# app/api/routes/results.py  (PRODUCTION – CORRECTED)

from fastapi import APIRouter, HTTPException
from pathlib import Path
from settings import settings

router = APIRouter()

@router.get("/{job_id}/results")
def job_results(job_id: str):
    # Closed model behavior:
    # input:  input/input.npz
    # output: output/input.npz  (same filename)

    output = Path(settings.JOB_BASE_DIR) / job_id / "output" / "input.npz"

    if not output.exists():
        raise HTTPException(status_code=404, detail="Results not ready")

    return {
        "job_id": job_id,
        "result_path": str(output),
    }
