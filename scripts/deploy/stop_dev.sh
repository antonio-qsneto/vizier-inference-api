#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Stop (hibernate) AWS environment resources without destroying Terraform state.

Usage:
  ./scripts/deploy/stop_dev.sh [options]

Options:
  --env <name>         Terraform environment (default: dev)
  --region <region>    AWS region (default: AWS_REGION or us-east-1)
  --api-count <n>      API desired count after stop (default: 0)
  --worker-count <n>   Worker desired count after stop (default: 0)
  --no-wait-ecs        Do not wait ECS services to stabilize
  --no-wait-rds        Do not wait RDS to stop
  --skip-ecs           Do not scale ECS services
  --skip-rds           Do not stop RDS
  --skip-gpu-asg       Do not change GPU ASG/schedule
  --help               Show this help
EOF
}

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-us-east-1}"
API_DESIRED_COUNT=0
WORKER_DESIRED_COUNT=0
WAIT_ECS=1
WAIT_RDS=1
SKIP_ECS=0
SKIP_RDS=0
SKIP_GPU_ASG=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENVIRONMENT="${2:-}"
      shift 2
      ;;
    --region)
      AWS_REGION="${2:-}"
      shift 2
      ;;
    --api-count)
      API_DESIRED_COUNT="${2:-0}"
      shift 2
      ;;
    --worker-count)
      WORKER_DESIRED_COUNT="${2:-0}"
      shift 2
      ;;
    --no-wait-ecs)
      WAIT_ECS=0
      shift
      ;;
    --no-wait-rds)
      WAIT_RDS=0
      shift
      ;;
    --skip-ecs)
      SKIP_ECS=1
      shift
      ;;
    --skip-rds)
      SKIP_RDS=1
      shift
      ;;
    --skip-gpu-asg)
      SKIP_GPU_ASG=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TF_DIR="${REPO_ROOT}/vizier-inference-infra/terraform/envs/${ENVIRONMENT}"
BACKEND_HCL="${TF_DIR}/backend.hcl"

if [[ ! -d "${TF_DIR}" ]]; then
  echo "Terraform env directory not found: ${TF_DIR}"
  exit 1
fi

if [[ ! -f "${BACKEND_HCL}" ]]; then
  echo "Missing backend config: ${BACKEND_HCL}"
  exit 1
fi

if ! command -v terraform >/dev/null 2>&1; then
  echo "terraform is required"
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "aws cli is required"
  exit 1
fi

terraform -chdir="${TF_DIR}" init -input=false -reconfigure -backend-config=backend.hcl >/dev/null

tf_out() {
  terraform -chdir="${TF_DIR}" output -raw "$1"
}

wait_rds_status() {
  local target_status="$1"
  local max_attempts="${2:-90}"   # ~30 min with 20s sleep
  local sleep_seconds="${3:-20}"
  local current_status=""

  for attempt in $(seq 1 "${max_attempts}"); do
    current_status="$(aws rds describe-db-instances \
      --region "${AWS_REGION}" \
      --db-instance-identifier "${RDS_INSTANCE_ID}" \
      --query 'DBInstances[0].DBInstanceStatus' \
      --output text)"

    echo "RDS status attempt ${attempt}/${max_attempts}: ${current_status} (target=${target_status})"
    if [[ "${current_status}" == "${target_status}" ]]; then
      return 0
    fi

    sleep "${sleep_seconds}"
  done

  echo "Timed out waiting RDS status '${target_status}'. Last status: ${current_status}"
  return 1
}

resolve_rds_identifier() {
  local raw="$1"

  # If it is already the instance identifier, this call works directly.
  if aws rds describe-db-instances \
    --region "${AWS_REGION}" \
    --db-instance-identifier "${raw}" \
    --query 'DBInstances[0].DBInstanceIdentifier' \
    --output text >/dev/null 2>&1; then
    echo "${raw}"
    return
  fi

  # Otherwise treat it as DbiResourceId (db-xxxx) and map to identifier.
  local resolved
  resolved="$(
    aws rds describe-db-instances \
      --region "${AWS_REGION}" \
      --query "DBInstances[?DbiResourceId=='${raw}'].DBInstanceIdentifier | [0]" \
      --output text 2>/dev/null || true
  )"

  if [[ -z "${resolved}" || "${resolved}" == "None" ]]; then
    echo ""
  else
    echo "${resolved}"
  fi
}

ECS_CLUSTER="$(tf_out ecs_gpu_cluster_name)"
API_SERVICE="$(tf_out ecs_fargate_django_service_name)"
WORKER_SERVICE="$(tf_out ecs_fargate_worker_service_name)"
GPU_ASG_NAME="$(tf_out ecs_gpu_asg_name)"
RDS_INSTANCE_RAW="$(tf_out rds_instance_identifier 2>/dev/null || tf_out rds_instance_id)"
RDS_INSTANCE_ID="$(resolve_rds_identifier "${RDS_INSTANCE_RAW}")"

if [[ -z "${RDS_INSTANCE_ID}" ]]; then
  echo "Could not resolve RDS instance identifier from output: ${RDS_INSTANCE_RAW}"
  exit 1
fi

echo "Stopping environment '${ENVIRONMENT}' in region '${AWS_REGION}'"
echo "ECS cluster: ${ECS_CLUSTER}"
echo "API service: ${API_SERVICE} -> desired=${API_DESIRED_COUNT}"
echo "Worker service: ${WORKER_SERVICE} -> desired=${WORKER_DESIRED_COUNT}"
echo "GPU ASG: ${GPU_ASG_NAME}"
echo "RDS: ${RDS_INSTANCE_ID} (source=${RDS_INSTANCE_RAW})"

if [[ "${SKIP_ECS}" != "1" ]]; then
  aws ecs update-service \
    --region "${AWS_REGION}" \
    --cluster "${ECS_CLUSTER}" \
    --service "${API_SERVICE}" \
    --desired-count "${API_DESIRED_COUNT}" >/dev/null

  aws ecs update-service \
    --region "${AWS_REGION}" \
    --cluster "${ECS_CLUSTER}" \
    --service "${WORKER_SERVICE}" \
    --desired-count "${WORKER_DESIRED_COUNT}" >/dev/null

  if [[ "${WAIT_ECS}" == "1" ]]; then
    echo "Waiting ECS services to stabilize..."
    aws ecs wait services-stable \
      --region "${AWS_REGION}" \
      --cluster "${ECS_CLUSTER}" \
      --services "${API_SERVICE}" "${WORKER_SERVICE}"
  fi
fi

if [[ "${SKIP_GPU_ASG}" != "1" ]]; then
  echo "Suspending GPU ASG scheduled actions and setting desired capacity to 0..."
  aws autoscaling suspend-processes \
    --region "${AWS_REGION}" \
    --auto-scaling-group-name "${GPU_ASG_NAME}" \
    --scaling-processes ScheduledActions >/dev/null || true

  aws autoscaling update-auto-scaling-group \
    --region "${AWS_REGION}" \
    --auto-scaling-group-name "${GPU_ASG_NAME}" \
    --min-size 0 \
    --desired-capacity 0 >/dev/null
fi

if [[ "${SKIP_RDS}" != "1" ]]; then
  DB_STATUS="$(aws rds describe-db-instances \
    --region "${AWS_REGION}" \
    --db-instance-identifier "${RDS_INSTANCE_ID}" \
    --query 'DBInstances[0].DBInstanceStatus' \
    --output text)"

  echo "Current RDS status: ${DB_STATUS}"

  case "${DB_STATUS}" in
    stopped)
      echo "RDS already stopped."
      ;;
    stopping)
      echo "RDS is already stopping."
      ;;
    starting)
      echo "RDS is starting. Waiting to become available before stopping..."
      aws rds wait db-instance-available \
        --region "${AWS_REGION}" \
        --db-instance-identifier "${RDS_INSTANCE_ID}"
      aws rds stop-db-instance \
        --region "${AWS_REGION}" \
        --db-instance-identifier "${RDS_INSTANCE_ID}" >/dev/null
      ;;
    *)
      aws rds stop-db-instance \
        --region "${AWS_REGION}" \
        --db-instance-identifier "${RDS_INSTANCE_ID}" >/dev/null
      ;;
  esac

  if [[ "${WAIT_RDS}" == "1" ]]; then
    echo "Waiting RDS to stop..."
    wait_rds_status "stopped"
  fi
fi

echo "Stop/hibernate completed."
echo "Note: RDS can remain stopped for up to 7 days before AWS auto-starts it."
