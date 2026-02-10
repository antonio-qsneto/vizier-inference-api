# app/api/routes/results.py
#
# This endpoint returns the output NPZ bytes to the caller (e.g., Django).
# Returning only a filesystem path would require the caller to also mount EFS.

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from settings import settings

router = APIRouter()


@router.get("/{job_id}/results")
def job_results(job_id: str):
    output_dir = Path(settings.JOB_BASE_DIR) / job_id / "output"

    # Prefer the most common filename, but be resilient to different model outputs.
    candidates = [
        output_dir / "input.npz",
    ]
    for c in candidates:
        if c.exists():
            return FileResponse(
                path=str(c),
                media_type="application/octet-stream",
                filename=c.name,
            )

    any_npz = next(output_dir.glob("*.npz"), None)
    if any_npz is not None and any_npz.exists():
        return FileResponse(
            path=str(any_npz),
            media_type="application/octet-stream",
            filename=any_npz.name,
        )

    raise HTTPException(status_code=404, detail="Results not ready")
