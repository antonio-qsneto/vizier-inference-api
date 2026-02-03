# app/api/services/storage.py
from pathlib import Path
import shutil

def create_job_dirs(jobs_root: str, job_id: str) -> dict:
    base = Path(jobs_root) / job_id
    input_dir = base / "input"
    output_dir = base / "output"

    input_dir.mkdir(parents=True, exist_ok=False)
    output_dir.mkdir(parents=True, exist_ok=False)

    return {
        "base": base,
        "input": input_dir,
        "output": output_dir,
    }

def write_status(job_dir: Path, status: str):
    status_file = job_dir / "status.txt"
    status_file.write_text(status)

def save_input_npz(input_dir: Path, file_bytes: bytes):
    path = input_dir / "input.npz"
    with open(path, "wb") as f:
        f.write(file_bytes)
