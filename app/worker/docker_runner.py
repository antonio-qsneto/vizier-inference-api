import os
import subprocess
from pathlib import Path

# ECR image for BiomedParse
MODEL_IMAGE = os.getenv(
    "MODEL_IMAGE",
    "996561439065.dkr.ecr.us-east-1.amazonaws.com/vizier-model:latest"
)

def run_biomedparse_container(job_dir: Path, memory_gb: int = 32):
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"

    cmd = [
        "docker", "run", "--rm",
        "--gpus", "all",                     # 🔑 enable GPU
        "-m", f"{memory_gb}G",
        "-v", f"{input_dir.resolve()}:/workspace/inputs",
        "-v", f"{output_dir.resolve()}:/workspace/outputs",
        MODEL_IMAGE,
        "/bin/bash", "-c",
        "export CUDA_VISIBLE_DEVICES=0 && sh predict.sh"
    ]

    subprocess.run(cmd, check=True)
