# app/api/routes/submit.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from services.jobs import create_job

router = APIRouter()

@router.post("/submit")
async def submit_job(file: UploadFile = File(...)):
    if not file.filename.endswith(".npz"): # type: ignore
        raise HTTPException(status_code=400, detail="Only .npz files are accepted")

    content = await file.read()
    job = create_job(content)
    return job
