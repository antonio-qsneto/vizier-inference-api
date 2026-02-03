from pathlib import Path

def write_status(job_dir: str, status: str):
    Path(job_dir, "status.txt").write_text(status)

def validate_output(job_dir: str) -> bool:
    return any((Path(job_dir) / "output").glob("*.npz"))
