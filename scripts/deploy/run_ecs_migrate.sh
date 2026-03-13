#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?AWS_REGION is required}"
: "${ECS_CLUSTER:?ECS_CLUSTER is required}"
: "${TASK_DEFINITION_ARN:?TASK_DEFINITION_ARN is required}"
: "${SUBNET_IDS:?SUBNET_IDS is required (comma-separated)}"
: "${SECURITY_GROUP_IDS:?SECURITY_GROUP_IDS is required (comma-separated)}"
: "${MIGRATION_CONTAINER_NAME:?MIGRATION_CONTAINER_NAME is required}"

NETWORK_CONFIG="awsvpcConfiguration={subnets=[${SUBNET_IDS}],securityGroups=[${SECURITY_GROUP_IDS}],assignPublicIp=DISABLED}"
OVERRIDES="$(cat <<JSON
{"containerOverrides":[{"name":"${MIGRATION_CONTAINER_NAME}","command":["python","manage.py","migrate","--noinput"]}]}
JSON
)"

echo "Running Django migration task..."
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
  echo "Failed to start migration task"
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
    --query "tasks[0].containers[?name=='${MIGRATION_CONTAINER_NAME}'].exitCode | [0]" \
    --output text
)"

if [[ "${EXIT_CODE}" != "0" ]]; then
  echo "Migration task failed with exit code: ${EXIT_CODE}"
  exit 1
fi

echo "Migration task completed successfully."
