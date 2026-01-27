import os
from pathlib import Path

JOB_BASE_DIR = Path(os.getenv("JOB_BASE_DIR", "/tmp/vizier-jobs"))
JOB_BASE_DIR.mkdir(parents=True, exist_ok=True)
