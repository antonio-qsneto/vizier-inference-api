from pathlib import Path

def set_status(job_dir: Path, status: str):
    (job_dir / "status.txt").write_text(status)

def validate_input(job_dir: Path):
    if not (job_dir / "input" / "input.npz").exists():
        raise FileNotFoundError("Missing input NPZ")

def validate_output(job_dir: Path):
    if not (job_dir / "output" / "input.npz").exists():
        raise FileNotFoundError("Missing output NPZ")
