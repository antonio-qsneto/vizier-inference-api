from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from services.job_store import get_job
from services.storage import get_object, object_exists, parse_s3_uri

router = APIRouter()


@router.get("/{job_id}/results")
def job_results(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "succeeded":
        raise HTTPException(status_code=404, detail="Results not ready")

    output_uri = job.get("output_s3_uri")
    if not output_uri:
        raise HTTPException(status_code=404, detail="Results not ready")

    bucket, key = parse_s3_uri(output_uri)
    if not object_exists(bucket, key):
        raise HTTPException(status_code=404, detail="Results not ready")

    obj = get_object(bucket, key)
    headers = {"Content-Disposition": 'attachment; filename="output.npz"'}
    return StreamingResponse(
        obj["Body"].iter_chunks(),
        media_type="application/octet-stream",
        headers=headers,
    )
