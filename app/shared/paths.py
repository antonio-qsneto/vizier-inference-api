import os
from pathlib import Path

# Default to the shared EFS mount used by ECS tasks
JOB_BASE_DIR = Path(os.getenv("JOB_BASE_DIR", "/mnt/efs/jobs"))
JOB_BASE_DIR.mkdir(parents=True, exist_ok=True)
