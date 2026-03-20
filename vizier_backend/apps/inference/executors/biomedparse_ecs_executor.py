"""BiomedParse execution adapter that runs GPU ECS tasks."""

from __future__ import annotations

import json
import logging
import textwrap
import time
from pathlib import Path
from typing import Callable

import boto3
from django.conf import settings

from services.s3_utils import S3Utils

from ..object_layout import output_mask_npz_key, output_summary_key

logger = logging.getLogger(__name__)


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
        import time
        import urllib.error
        import urllib.parse
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
            payload = path.read_bytes()
            for attempt in range(1, 4):
                try:
                    req = urllib.request.Request(
                        url,
                        data=payload,
                        method="PUT",
                        headers={"Content-Type": content_type},
                    )
                    with urllib.request.urlopen(req) as response:
                        response.read()
                    return
                except urllib.error.HTTPError as exc:
                    error_body = exc.read().decode("utf-8", errors="ignore")
                    print(json.dumps({
                        "event": "s3_upload_http_error",
                        "job_id": os.environ["JOB_ID"],
                        "attempt": attempt,
                        "status": exc.code,
                        "reason": exc.reason,
                        "path": str(path),
                        "content_type": content_type,
                        "url_host": urllib.parse.urlsplit(url).netloc,
                        "response_body": error_body[:2000],
                    }))
                    if attempt >= 3:
                        raise
                    time.sleep(min(2 ** attempt, 10))

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


class BiomedParseECSExecutor:
    """Runs BiomedParse in ECS GPU tasks and materializes output locally."""

    def __init__(self):
        self.s3 = S3Utils()
        self.ecs_client = boto3.client("ecs", region_name=settings.AWS_REGION)
        self.cluster = str(getattr(settings, "BIO_ECS_CLUSTER", "") or "").strip()
        self.task_definition = str(getattr(settings, "BIO_ECS_TASK_DEFINITION", "") or "").strip()
        self.capacity_provider = str(getattr(settings, "BIO_ECS_CAPACITY_PROVIDER", "") or "").strip()
        self.subnets = [
            token.strip()
            for token in str(getattr(settings, "BIO_ECS_SUBNETS", "") or "").split(",")
            if token.strip()
        ]
        self.security_groups = [
            token.strip()
            for token in str(getattr(settings, "BIO_ECS_SECURITY_GROUPS", "") or "").split(",")
            if token.strip()
        ]
        self.container_name = str(getattr(settings, "BIO_ECS_CONTAINER_NAME", "biomedparse") or "biomedparse")
        self.poll_seconds = int(getattr(settings, "BIO_ECS_TASK_POLL_SECONDS", 15))
        self.timeout_seconds = int(getattr(settings, "BIO_ECS_TASK_TIMEOUT_SECONDS", 3600))
        configured_presign_seconds = int(getattr(settings, "BIO_ECS_PRESIGNED_URL_EXPIRES_SECONDS", 0) or 0)
        fallback_presign_seconds = max(self.timeout_seconds + 1800, 7200)
        self.presign_expires_seconds = max(
            900,
            min(604800, configured_presign_seconds if configured_presign_seconds > 0 else fallback_presign_seconds),
        )
        self.task_not_found_grace_seconds = max(
            0,
            int(getattr(settings, "BIO_ECS_TASK_NOT_FOUND_GRACE_SECONDS", 60) or 60),
        )

    def _validate_config(self) -> None:
        missing = []
        if not self.cluster:
            missing.append("BIO_ECS_CLUSTER")
        if not self.task_definition:
            missing.append("BIO_ECS_TASK_DEFINITION")
        if not self.capacity_provider:
            missing.append("BIO_ECS_CAPACITY_PROVIDER")
        if not self.subnets:
            missing.append("BIO_ECS_SUBNETS")
        if not self.security_groups:
            missing.append("BIO_ECS_SECURITY_GROUPS")
        if missing:
            raise ValueError(f"Missing ECS executor config: {', '.join(missing)}")

    def run(
        self,
        *,
        job_id: str,
        tenant_id: str,
        normalized_input_key: str,
        work_dir: str,
        requested_device: str = "cuda",
        slice_batch_size: int | None = None,
        on_poll: Callable[[], None] | None = None,
    ) -> dict[str, str]:
        self._validate_config()

        mask_npz_key = output_mask_npz_key(tenant_id, job_id)
        summary_key = output_summary_key(tenant_id, job_id)
        input_download_url = self.s3.generate_presigned_url(
            normalized_input_key,
            expires_in=self.presign_expires_seconds,
            method="get_object",
        )
        output_upload_url = self.s3.generate_presigned_url(
            mask_npz_key,
            expires_in=self.presign_expires_seconds,
            method="put_object",
            extra_params={"ContentType": "application/octet-stream"},
        )
        summary_upload_url = self.s3.generate_presigned_url(
            summary_key,
            expires_in=self.presign_expires_seconds,
            method="put_object",
            extra_params={"ContentType": "application/json"},
        )

        environment = [
            {"name": "JOB_ID", "value": job_id},
            {"name": "INPUT_DOWNLOAD_URL", "value": input_download_url},
            {"name": "OUTPUT_UPLOAD_URL", "value": output_upload_url},
            {"name": "SUMMARY_UPLOAD_URL", "value": summary_upload_url},
            {"name": "REQUESTED_DEVICE", "value": (requested_device or "cuda").strip().lower()},
            {"name": "JOB_WORKDIR", "value": f"/tmp/jobs/{job_id}"},
        ]
        if slice_batch_size is not None:
            environment.append({"name": "SLICE_BATCH_SIZE", "value": str(int(slice_batch_size))})

        response = self.ecs_client.run_task(
            cluster=self.cluster,
            taskDefinition=self.task_definition,
            capacityProviderStrategy=[
                {
                    "capacityProvider": self.capacity_provider,
                    "weight": 1,
                }
            ],
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": self.subnets,
                    "securityGroups": self.security_groups,
                    "assignPublicIp": "DISABLED",
                }
            },
            overrides={
                "containerOverrides": [
                    {
                        "name": self.container_name,
                        "command": [_container_command()],
                        "environment": environment,
                    }
                ]
            },
        )
        if response.get("failures"):
            raise RuntimeError(f"ECS run_task failed: {json.dumps(response['failures'])}")

        task_arn = response["tasks"][0]["taskArn"]
        started = time.monotonic()
        task_missing_since: float | None = None
        while True:
            task_resp = self.ecs_client.describe_tasks(cluster=self.cluster, tasks=[task_arn])
            tasks = task_resp.get("tasks", [])
            if not tasks:
                if on_poll is not None:
                    on_poll()

                has_mask_output = self.s3.object_exists(mask_npz_key)
                has_summary_output = self.s3.object_exists(summary_key)
                if has_mask_output and has_summary_output:
                    logger.warning(
                        "ECS task missing in describe_tasks, but outputs already exist; proceeding as success",
                        extra={
                            "job_id": job_id,
                            "task_arn": task_arn,
                            "mask_npz_key": mask_npz_key,
                            "summary_key": summary_key,
                        },
                    )
                    break

                if task_missing_since is None:
                    task_missing_since = time.monotonic()

                missing_seconds = time.monotonic() - task_missing_since
                if missing_seconds <= self.task_not_found_grace_seconds:
                    if time.monotonic() - started > self.timeout_seconds:
                        raise TimeoutError(f"ECS task timeout for job {job_id}")
                    time.sleep(max(1, self.poll_seconds))
                    continue

                failures = task_resp.get("failures", [])
                failure_blob = json.dumps(failures) if failures else "[]"
                raise RuntimeError(f"ECS task not found: {task_arn}; failures={failure_blob}")
            task = tasks[0]
            task_missing_since = None

            if on_poll is not None:
                on_poll()

            if task.get("lastStatus") == "STOPPED":
                containers = task.get("containers", [])
                container = next(
                    (item for item in containers if item.get("name") == self.container_name),
                    {},
                )
                exit_code = container.get("exitCode")
                reason = container.get("reason") or task.get("stoppedReason", "")
                if exit_code not in (0, None):
                    raise RuntimeError(f"ECS task failed for {job_id}, exit_code={exit_code}, reason={reason}")
                break

            if time.monotonic() - started > self.timeout_seconds:
                raise TimeoutError(f"ECS task timeout for job {job_id}")
            time.sleep(max(1, self.poll_seconds))

        if not self.s3.object_exists(mask_npz_key):
            raise RuntimeError(f"Expected mask object missing in S3: {mask_npz_key}")
        if not self.s3.object_exists(summary_key):
            raise RuntimeError(f"Expected summary object missing in S3: {summary_key}")

        Path(work_dir).mkdir(parents=True, exist_ok=True)
        mask_npz_local = str(Path(work_dir) / "mask.npz")
        summary_local = str(Path(work_dir) / "summary.json")
        if not self.s3.download_file(mask_npz_key, mask_npz_local):
            raise RuntimeError(f"Failed to download mask output from {mask_npz_key}")
        if not self.s3.download_file(summary_key, summary_local):
            raise RuntimeError(f"Failed to download summary output from {summary_key}")

        return {
            "gpu_task_arn": task_arn,
            "mask_npz_key": mask_npz_key,
            "summary_key": summary_key,
            "mask_npz_local": mask_npz_local,
            "summary_json_local": summary_local,
        }
