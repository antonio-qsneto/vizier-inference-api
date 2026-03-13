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
RUN_TASK_OUTPUT="$(
  aws ecs run-task \
    --region "${AWS_REGION}" \
    --cluster "${ECS_CLUSTER}" \
    --launch-type FARGATE \
    --task-definition "${TASK_DEFINITION_ARN}" \
    --network-configuration "${NETWORK_CONFIG}" \
    --overrides "${OVERRIDES}" \
    --output json
)"
export RUN_TASK_OUTPUT

FAILURE_COUNT="$(
  python3 - <<'PY'
import json, os
payload = json.loads(os.environ["RUN_TASK_OUTPUT"])
print(len(payload.get("failures", [])))
PY
)"
if [[ "${FAILURE_COUNT}" != "0" ]]; then
  echo "Failed to start bootstrap task (run-task failures detected):"
  echo "${RUN_TASK_OUTPUT}"
  exit 1
fi

TASK_ARN="$(
  python3 - <<'PY'
import json, os
payload = json.loads(os.environ["RUN_TASK_OUTPUT"])
tasks = payload.get("tasks") or []
print(tasks[0].get("taskArn") if tasks else "")
PY
)"

if [[ -z "${TASK_ARN}" || "${TASK_ARN}" == "None" ]]; then
  echo "Failed to start bootstrap task"
  exit 1
fi

aws ecs wait tasks-stopped \
  --region "${AWS_REGION}" \
  --cluster "${ECS_CLUSTER}" \
  --tasks "${TASK_ARN}"

DESCRIBE_TASK_OUTPUT="$(
  aws ecs describe-tasks \
    --region "${AWS_REGION}" \
    --cluster "${ECS_CLUSTER}" \
    --tasks "${TASK_ARN}" \
    --output json
)"
export DESCRIBE_TASK_OUTPUT

EXIT_CODE="$(
  python3 - <<'PY'
import json, os
payload = json.loads(os.environ["DESCRIBE_TASK_OUTPUT"])
tasks = payload.get("tasks") or []
if not tasks:
    print("None")
    raise SystemExit(0)

task = tasks[0]
target = os.environ.get("BOOTSTRAP_CONTAINER_NAME")
containers = task.get("containers") or []
container = next((c for c in containers if c.get("name") == target), None)
if container is None and containers:
    container = containers[0]
print(container.get("exitCode") if container else "None")
PY
)"

if [[ "${EXIT_CODE}" != "0" ]]; then
  STOPPED_REASON="$(
    python3 - <<'PY'
import json, os
payload = json.loads(os.environ["DESCRIBE_TASK_OUTPUT"])
tasks = payload.get("tasks") or []
print((tasks[0].get("stoppedReason") if tasks else "") or "")
PY
  )"

  echo "Bootstrap task failed with exit code: ${EXIT_CODE}"
  echo "Stopped reason: ${STOPPED_REASON}"
  echo "Container statuses:"
  aws ecs describe-tasks \
    --region "${AWS_REGION}" \
    --cluster "${ECS_CLUSTER}" \
    --tasks "${TASK_ARN}" \
    --query 'tasks[0].containers[*].{name:name,lastStatus:lastStatus,exitCode:exitCode,reason:reason}' \
    --output table || true
  exit 1
fi

echo "Bootstrap task completed successfully."
