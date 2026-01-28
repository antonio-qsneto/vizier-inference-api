import os
import time
from pathlib import Path
from typing import List

import boto3

ecs = boto3.client("ecs", region_name=os.getenv("AWS_REGION", "us-east-1"))


def _split_csv_env(name: str) -> List[str]:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return [item.strip() for item in val.split(",") if item.strip()]


def run_biomedparse_task(job_dir: Path, timeout_sec: int = 1800, poll_sec: int = 5):
    """
    Launch a dedicated BiomedParse ECS task for a single job and block until it finishes.

    Required env vars (set on the worker task definition):
      ECS_CLUSTER            - ECS cluster name
      BIO_TASK_DEF           - Task definition ARN or family:revision for the BiomedParse task
      TASK_SUBNETS           - Comma-separated private subnet IDs
      TASK_SECURITY_GROUPS   - Comma-separated security group IDs
      AWS_REGION             - AWS region (used by boto3 client)
      BIO_CONTAINER_NAME     - (optional) container name inside the BiomedParse task (default: biomedparse)
      JOB_BASE_DIR           - base jobs dir (default: /mnt/efs/jobs)
    """
    cluster = os.environ["ECS_CLUSTER"]
    task_def = os.environ["BIO_TASK_DEF"]
    subnets = _split_csv_env("TASK_SUBNETS")
    sgs = _split_csv_env("TASK_SECURITY_GROUPS")
    container_name = os.getenv("BIO_CONTAINER_NAME", "biomedparse")
    job_base = os.getenv("JOB_BASE_DIR", "/mnt/efs/jobs")

    capacity_provider = os.getenv("CAPACITY_PROVIDER")

    overrides = {
        "containerOverrides": [
            {
                "name": container_name,
                "environment": [
                    {"name": "JOB_DIR", "value": str(job_dir)},
                    {"name": "JOB_BASE_DIR", "value": job_base},
                ],
            }
        ]
    }

    run_args = {
        "cluster": cluster,
        "taskDefinition": task_def,
        "count": 1,
        "networkConfiguration": {
            "awsvpcConfiguration": {
                "subnets": subnets,
                "securityGroups": sgs,
                "assignPublicIp": "DISABLED",
            }
        },
        "overrides": overrides,
    }

    if capacity_provider:
        run_args["capacityProviderStrategy"] = [
            {"capacityProvider": capacity_provider, "weight": 1}
        ]
    else:
        run_args["launchType"] = "EC2"

    resp = ecs.run_task(**run_args)

    if resp.get("failures"):
        reasons = "; ".join(f"{f.get('arn')}: {f.get('reason')}" for f in resp["failures"])
        raise RuntimeError(f"Failed to start BiomedParse task: {reasons}")

    task_arn = resp["tasks"][0]["taskArn"]
    start = time.time()

    while True:
        desc = ecs.describe_tasks(cluster=cluster, tasks=[task_arn])
        task = desc["tasks"][0]

        if task["lastStatus"] == "STOPPED":
            container = next(c for c in task["containers"] if c["name"] == container_name)
            exit_code = container.get("exitCode", 1)
            reason = container.get("reason", "")
            if exit_code != 0:
                raise RuntimeError(f"BiomedParse task failed (exit {exit_code}): {reason}")
            return

        if time.time() - start > timeout_sec:
            raise TimeoutError(f"BiomedParse task {task_arn} did not complete within {timeout_sec}s")

        time.sleep(poll_sec)
