from dotenv import load_dotenv
load_dotenv()

import shutil
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path

from app.infra.sqs_client import enqueue_job
from app.shared.paths import JOB_BASE_DIR

app = FastAPI(title="Vizier Inference API (DEV)")

@app.post("/infer")
async def infer(file: UploadFile):
    if not file.filename.endswith(".npz"):
        raise HTTPException(status_code=400, detail="Only .npz files are supported")

    import uuid
    job_id = str(uuid.uuid4())
    job_dir = JOB_BASE_DIR / job_id
    (job_dir / "input").mkdir(parents=True, exist_ok=True)
    (job_dir / "output").mkdir(parents=True, exist_ok=True)

    (job_dir / "status.txt").write_text("pending")

    input_path = job_dir / "input" / "input.npz"
    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    enqueue_job(job_id=job_id, job_dir=str(job_dir))

    return JSONResponse({"job_id": job_id, "status": "submitted"})
