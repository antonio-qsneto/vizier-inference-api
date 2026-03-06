from __future__ import annotations

import textwrap
import time
from typing import Callable

import boto3

from settings import settings

_ecs = boto3.client("ecs", region_name=settings.AWS_REGION)


def _container_command() -> str:
    return textwrap.dedent(
        """
        set -eu
        export JOB_WORKDIR="${JOB_WORKDIR:-/tmp/job}"
        mkdir -p "$JOB_WORKDIR"

        python - <<'PY'
        import json
        import os
        import pathlib
        import shutil
        import urllib.request

        workdir = pathlib.Path(os.environ["JOB_WORKDIR"])
        input_path = workdir / "input.npz"
        with urllib.request.urlopen(os.environ["INPUT_DOWNLOAD_URL"]) as response:
            with input_path.open("wb") as output_file:
                shutil.copyfileobj(response, output_file)
        print(json.dumps({
            "event": "input_downloaded",
            "job_id": os.environ["JOB_ID"],
            "bytes": input_path.stat().st_size,
            "path": str(input_path),
        }))
        PY

        INFER_ARGS="--input-file $JOB_WORKDIR/input.npz --output-file $JOB_WORKDIR/output.npz --device ${REQUESTED_DEVICE:-cuda} --summary-file $JOB_WORKDIR/summary.json"
        if [ -n "${SLICE_BATCH_SIZE:-}" ]; then
          INFER_ARGS="$INFER_ARGS --slice-batch-size $SLICE_BATCH_SIZE"
        fi

        echo "{\"event\":\"inference_started\",\"job_id\":\"$JOB_ID\",\"device\":\"${REQUESTED_DEVICE:-cuda}\"}"
        python /opt/BiomedParse/inference.py $INFER_ARGS

        python - <<'PY'
        import json
        import os
        import pathlib
        import urllib.request

        workdir = pathlib.Path(os.environ["JOB_WORKDIR"])
        output_path = workdir / "output.npz"
        summary_path = workdir / "summary.json"
        if not summary_path.exists():
            summary_path.write_text(json.dumps({
                "job_id": os.environ["JOB_ID"],
                "generated_by_worker": True,
                "note": "BiomedParse runner did not create summary.json; worker generated a fallback summary.",
            }))

        def upload(path: pathlib.Path, url: str, content_type: str):
            req = urllib.request.Request(
                url,
                data=path.read_bytes(),
                method="PUT",
                headers={"Content-Type": content_type},
            )
            with urllib.request.urlopen(req) as response:
                response.read()

        upload(output_path, os.environ["OUTPUT_UPLOAD_URL"], "application/octet-stream")
        upload(summary_path, os.environ["SUMMARY_UPLOAD_URL"], "application/json")
        print(json.dumps({
            "event": "artifacts_uploaded",
            "job_id": os.environ["JOB_ID"],
            "output_bytes": output_path.stat().st_size,
            "summary_bytes": summary_path.stat().st_size,
        }))
        PY

        rm -rf "$JOB_WORKDIR"
        """
    ).strip()


def run_biomedparse_task(
    *,
    job_id: str,
    input_download_url: str,
    output_upload_url: str,
    summary_upload_url: str,
    requested_device: str,
    slice_batch_size: int | None,
) -> str:
    subnets = [item for item in settings.TASK_SUBNETS.split(",") if item]
    security_groups = [item for item in settings.TASK_SECURITY_GROUPS.split(",") if item]

    environment = [
        {"name": "JOB_ID", "value": job_id},
        {"name": "INPUT_DOWNLOAD_URL", "value": input_download_url},
        {"name": "OUTPUT_UPLOAD_URL", "value": output_upload_url},
        {"name": "SUMMARY_UPLOAD_URL", "value": summary_upload_url},
        {"name": "REQUESTED_DEVICE", "value": requested_device or settings.DEFAULT_REQUESTED_DEVICE},
        {"name": "JOB_WORKDIR", "value": f"/tmp/jobs/{job_id}"},
    ]
    if slice_batch_size is not None:
        environment.append({"name": "SLICE_BATCH_SIZE", "value": str(slice_batch_size)})

    resp = _ecs.run_task(
        cluster=settings.ECS_CLUSTER,
        taskDefinition=settings.BIO_TASK_DEF,
        capacityProviderStrategy=[
            {
                "capacityProvider": settings.CAPACITY_PROVIDER,
                "weight": 1,
            }
        ],
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": subnets,
                "securityGroups": security_groups,
                "assignPublicIp": "DISABLED",
            }
        },
        overrides={
            "containerOverrides": [
                {
                    "name": settings.BIO_CONTAINER_NAME,
                    "command": [_container_command()],
                    "environment": environment,
                }
            ]
        },
    )

    if resp.get("failures"):
        raise RuntimeError(f"ECS run_task failed: {resp['failures']}")

    return resp["tasks"][0]["taskArn"]


def wait_for_task(
    task_arn: str,
    on_tick: Callable[[dict], None] | None = None,
) -> dict:
    while True:
        response = _ecs.describe_tasks(
            cluster=settings.ECS_CLUSTER,
            tasks=[task_arn],
        )
        tasks = response.get("tasks", [])
        if not tasks:
            raise RuntimeError(f"ECS task not found: {task_arn}")
        task = tasks[0]
        if on_tick is not None:
            on_tick(task)
        if task.get("lastStatus") == "STOPPED":
            return task
        time.sleep(settings.ECS_TASK_POLL_SECONDS)
