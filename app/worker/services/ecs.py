import boto3
from settings import settings

_ecs = boto3.client("ecs", region_name=settings.AWS_REGION)

def run_biomedparse_task(job_id: str) -> str:
    subnets = settings.TASK_SUBNETS.split(",")
    security_groups = settings.TASK_SECURITY_GROUPS.split(",")

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

                    "command": [
                        "/bin/bash",
                        "-c",
                        (
                            "set -e && "
                            "echo \"JOB_BASE_DIR=$JOB_BASE_DIR\" && "
                            "echo \"JOB_ID=$JOB_ID\" && "

                            # prepare inputs
                            "rm -rf /workspace/inputs /workspace/outputs && "
                            "mkdir -p /workspace/inputs && "
                            "cp -r \"$JOB_BASE_DIR/$JOB_ID/input\"/* /workspace/inputs/ && "

                            # run model
                            "export CUDA_VISIBLE_DEVICES=0 && "
                            "sh predict.sh && "

                            # persist outputs
                            "mkdir -p \"$JOB_BASE_DIR/$JOB_ID/output\" && "
                            "cp -r /workspace/outputs/* \"$JOB_BASE_DIR/$JOB_ID/output/\""
                        )
                        ],

                    "environment": [
                        {"name": "JOB_ID", "value": job_id}
                    ],
                }
            ]
        },
    )

    if resp.get("failures"):
        raise RuntimeError(f"ECS run_task failed: {resp['failures']}")

    return resp["tasks"][0]["taskArn"]

def wait_for_task(task_arn: str):
    waiter = _ecs.get_waiter("tasks_stopped")
    waiter.wait(
        cluster=settings.ECS_CLUSTER,
        tasks=[task_arn],
    )