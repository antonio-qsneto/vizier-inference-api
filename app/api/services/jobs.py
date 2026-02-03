# app/api/services/jobs.py
import uuid
from settings import settings
from services.storage import create_job_dirs, write_status, save_input_npz
from services.sqs import enqueue_job

def create_job(npz_bytes: bytes) -> dict:
    job_id = str(uuid.uuid4())

    dirs = create_job_dirs(settings.JOB_BASE_DIR, job_id)
    save_input_npz(dirs["input"], npz_bytes)
    write_status(dirs["base"], "pending")

    enqueue_job(job_id, str(dirs["base"]))

    return {
        "job_id": job_id,
        "status": "pending",
    }
