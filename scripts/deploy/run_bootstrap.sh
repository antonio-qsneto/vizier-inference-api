#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?AWS_REGION is required}"
: "${ECS_CLUSTER:?ECS_CLUSTER is required}"
: "${TASK_DEFINITION_ARN:?TASK_DEFINITION_ARN is required}"
: "${SUBNET_IDS:?SUBNET_IDS is required (comma-separated)}"
: "${SECURITY_GROUP_IDS:?SECURITY_GROUP_IDS is required (comma-separated)}"
: "${BOOTSTRAP_CONTAINER_NAME:?BOOTSTRAP_CONTAINER_NAME is required}"
: "${BOOTSTRAP_ADMIN_EMAIL:?BOOTSTRAP_ADMIN_EMAIL is required}"

MODEL_NAME="${BOOTSTRAP_MODEL_NAME:-biomedparse}"
MODEL_VERSION="${BOOTSTRAP_MODEL_VERSION:-v1}"
BOOTSTRAP_FIRST_NAME="${BOOTSTRAP_FIRST_NAME:-Bootstrap}"
BOOTSTRAP_LAST_NAME="${BOOTSTRAP_LAST_NAME:-Admin}"
BOOTSTRAP_ROLE="${BOOTSTRAP_ROLE:-INDIVIDUAL}"
BOOTSTRAP_CREATE_USER_IF_MISSING="${BOOTSTRAP_CREATE_USER_IF_MISSING:-1}"
BOOTSTRAP_MAKE_SUPERUSER="${BOOTSTRAP_MAKE_SUPERUSER:-0}"

export MODEL_NAME
export MODEL_VERSION
export BOOTSTRAP_FIRST_NAME
export BOOTSTRAP_LAST_NAME
export BOOTSTRAP_ROLE
export BOOTSTRAP_CREATE_USER_IF_MISSING
export BOOTSTRAP_MAKE_SUPERUSER
export BOOTSTRAP_CONTAINER_NAME
export BOOTSTRAP_ADMIN_EMAIL

NETWORK_CONFIG="awsvpcConfiguration={subnets=[${SUBNET_IDS}],securityGroups=[${SECURITY_GROUP_IDS}],assignPublicIp=DISABLED}"
OVERRIDES="$(python3 - <<'PY'
import json
import os

command = [
    "python",
    "manage.py",
    "bootstrap_initial_tenant_admin",
    "--email",
    os.environ["BOOTSTRAP_ADMIN_EMAIL"],
    "--model-name",
    os.environ["MODEL_NAME"],
    "--model-version",
    os.environ["MODEL_VERSION"],
    "--first-name",
    os.environ["BOOTSTRAP_FIRST_NAME"],
    "--last-name",
    os.environ["BOOTSTRAP_LAST_NAME"],
    "--role",
    os.environ["BOOTSTRAP_ROLE"],
]
if os.environ.get("BOOTSTRAP_CREATE_USER_IF_MISSING", "1") == "1":
    command.append("--create-user-if-missing")
if os.environ.get("BOOTSTRAP_MAKE_SUPERUSER", "0") == "1":
    command.append("--make-superuser")

print(
    json.dumps(
        {
            "containerOverrides": [
                {
                    "name": os.environ["BOOTSTRAP_CONTAINER_NAME"],
                    "command": command,
                }
            ]
        }
    )
)
PY
)"

echo "Running bootstrap task..."
TASK_ARN="$(
  aws ecs run-task \
    --region "${AWS_REGION}" \
    --cluster "${ECS_CLUSTER}" \
    --launch-type FARGATE \
    --task-definition "${TASK_DEFINITION_ARN}" \
    --network-configuration "${NETWORK_CONFIG}" \
    --overrides "${OVERRIDES}" \
    --query 'tasks[0].taskArn' \
    --output text
)"

if [[ -z "${TASK_ARN}" || "${TASK_ARN}" == "None" ]]; then
  echo "Failed to start bootstrap task"
  exit 1
fi

aws ecs wait tasks-stopped \
  --region "${AWS_REGION}" \
  --cluster "${ECS_CLUSTER}" \
  --tasks "${TASK_ARN}"

EXIT_CODE="$(
  aws ecs describe-tasks \
    --region "${AWS_REGION}" \
    --cluster "${ECS_CLUSTER}" \
    --tasks "${TASK_ARN}" \
    --query "tasks[0].containers[?name=='${BOOTSTRAP_CONTAINER_NAME}'].exitCode | [0]" \
    --output text
)"

if [[ "${EXIT_CODE}" != "0" ]]; then
  echo "Bootstrap task failed with exit code: ${EXIT_CODE}"
  exit 1
fi

echo "Bootstrap task completed successfully."
