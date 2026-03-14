#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Sync Amplify branch environment variables from Terraform outputs.

Usage:
  ./scripts/deploy/sync_amplify_env.sh [options]

Options:
  --env <dev|prod>              Terraform environment (default: dev)
  --app-id <id>                 Amplify App ID (or AMPLIFY_APP_ID env)
  --branch <name>               Amplify branch (default: main)
  --frontend-base-url <url>     Frontend URL used to build redirect/logout URLs.
                                If omitted, reads branch.webUrl from Amplify.
  --api-scheme <http|https>     Scheme for VITE_API_BASE_URL (default: http)
  --async-upload <true|false>   Value for VITE_USE_ASYNC_S3_UPLOAD (default: true)
  --dry-run                     Print merged variables without applying
  --help                        Show this help

Examples:
  ./scripts/deploy/sync_amplify_env.sh --env dev --app-id d2fezrl1u8wfmh --branch main
  ./scripts/deploy/sync_amplify_env.sh --env prod --app-id d2fezrl1u8wfmh --api-scheme https
EOF
}

ENVIRONMENT="dev"
APP_ID="${AMPLIFY_APP_ID:-}"
BRANCH="main"
FRONTEND_BASE_URL=""
API_SCHEME="http"
ASYNC_UPLOAD="true"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENVIRONMENT="${2:-}"
      shift 2
      ;;
    --app-id)
      APP_ID="${2:-}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:-}"
      shift 2
      ;;
    --frontend-base-url)
      FRONTEND_BASE_URL="${2:-}"
      shift 2
      ;;
    --api-scheme)
      API_SCHEME="${2:-}"
      shift 2
      ;;
    --async-upload)
      ASYNC_UPLOAD="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
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

if [[ "${ENVIRONMENT}" != "dev" && "${ENVIRONMENT}" != "prod" ]]; then
  echo "--env must be dev or prod"
  exit 1
fi

if [[ -z "${APP_ID}" ]]; then
  echo "--app-id is required (or set AMPLIFY_APP_ID)"
  exit 1
fi

if [[ "${API_SCHEME}" != "http" && "${API_SCHEME}" != "https" ]]; then
  echo "--api-scheme must be http or https"
  exit 1
fi

for cmd in aws terraform jq; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "${cmd} is required"
    exit 1
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TF_ENV_DIR="${REPO_ROOT}/vizier-inference-infra/terraform/envs/${ENVIRONMENT}"
BACKEND_HCL="${TF_ENV_DIR}/backend.hcl"

if [[ -n "${TF_STATE_BUCKET:-}" ]]; then
  INIT_REGION="${AWS_REGION:-us-east-1}"
  BACKEND_ARGS=(
    "-backend-config=bucket=${TF_STATE_BUCKET}"
    "-backend-config=key=envs/${ENVIRONMENT}/terraform.tfstate"
    "-backend-config=region=${INIT_REGION}"
    "-backend-config=encrypt=true"
  )
  if [[ -n "${TF_STATE_LOCK_TABLE:-}" ]]; then
    BACKEND_ARGS+=("-backend-config=dynamodb_table=${TF_STATE_LOCK_TABLE}")
  fi
  terraform -chdir="${TF_ENV_DIR}" init -input=false -reconfigure "${BACKEND_ARGS[@]}" >/dev/null
elif [[ -f "${BACKEND_HCL}" ]]; then
  terraform -chdir="${TF_ENV_DIR}" init -input=false -reconfigure -backend-config=backend.hcl >/dev/null
else
  echo "Terraform backend config not found: ${BACKEND_HCL}"
  echo "Provide TF_STATE_BUCKET/TF_STATE_LOCK_TABLE env vars or create backend.hcl first."
  exit 1
fi

REGION="$(terraform -chdir="${TF_ENV_DIR}" output -raw region)"
ALB_DNS_NAME="$(terraform -chdir="${TF_ENV_DIR}" output -raw alb_dns_name)"
COGNITO_USER_POOL_ID="$(terraform -chdir="${TF_ENV_DIR}" output -raw cognito_user_pool_id)"
COGNITO_CLIENT_ID="$(terraform -chdir="${TF_ENV_DIR}" output -raw cognito_user_pool_client_id)"
COGNITO_DOMAIN_PREFIX="$(terraform -chdir="${TF_ENV_DIR}" output -raw cognito_user_pool_domain)"

if [[ -z "${FRONTEND_BASE_URL}" ]]; then
  FRONTEND_BASE_URL="$(aws amplify get-branch \
    --app-id "${APP_ID}" \
    --branch-name "${BRANCH}" \
    --query 'branch.webUrl' \
    --output text 2>/dev/null || true)"
fi

if [[ -z "${FRONTEND_BASE_URL}" || "${FRONTEND_BASE_URL}" == "None" || "${FRONTEND_BASE_URL}" == "null" ]]; then
  echo "Could not resolve frontend base URL. Use --frontend-base-url."
  exit 1
fi

FRONTEND_BASE_URL="${FRONTEND_BASE_URL%/}"
REDIRECT_URI="${FRONTEND_BASE_URL}/auth/callback"
LOGOUT_URI="${FRONTEND_BASE_URL}/login"
COGNITO_DOMAIN="https://${COGNITO_DOMAIN_PREFIX}.auth.${REGION}.amazoncognito.com"

NEW_VARS_JSON="$(jq -n \
  --arg api_base_url "${API_SCHEME}://${ALB_DNS_NAME}" \
  --arg async_upload "${ASYNC_UPLOAD}" \
  --arg cognito_region "${REGION}" \
  --arg cognito_user_pool_id "${COGNITO_USER_POOL_ID}" \
  --arg cognito_client_id "${COGNITO_CLIENT_ID}" \
  --arg cognito_domain "${COGNITO_DOMAIN}" \
  --arg redirect_uri "${REDIRECT_URI}" \
  --arg logout_uri "${LOGOUT_URI}" \
  '{
    VITE_API_BASE_URL: $api_base_url,
    VITE_USE_ASYNC_S3_UPLOAD: $async_upload,
    VITE_COGNITO_REGION: $cognito_region,
    VITE_COGNITO_USER_POOL_ID: $cognito_user_pool_id,
    VITE_COGNITO_CLIENT_ID: $cognito_client_id,
    VITE_COGNITO_DOMAIN: $cognito_domain,
    VITE_COGNITO_REDIRECT_URI: $redirect_uri,
    VITE_COGNITO_LOGOUT_URI: $logout_uri
  }')"

EXISTING_VARS_JSON="$(aws amplify get-branch \
  --app-id "${APP_ID}" \
  --branch-name "${BRANCH}" \
  --query 'branch.environmentVariables' \
  --output json 2>/dev/null || echo '{}')"

if [[ -z "${EXISTING_VARS_JSON}" || "${EXISTING_VARS_JSON}" == "null" ]]; then
  EXISTING_VARS_JSON='{}'
fi

MERGED_VARS_JSON="$(jq -s '.[0] * .[1]' <(echo "${EXISTING_VARS_JSON}") <(echo "${NEW_VARS_JSON}"))"

echo "Amplify app: ${APP_ID}"
echo "Amplify branch: ${BRANCH}"
echo "Frontend base URL: ${FRONTEND_BASE_URL}"
echo "Merged VITE vars to apply:"
echo "${MERGED_VARS_JSON}" | jq '.'

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "Dry-run mode enabled. No changes applied."
  exit 0
fi

TMP_VARS_FILE="$(mktemp)"
trap 'rm -f "${TMP_VARS_FILE}"' EXIT
echo "${MERGED_VARS_JSON}" > "${TMP_VARS_FILE}"

aws amplify update-branch \
  --app-id "${APP_ID}" \
  --branch-name "${BRANCH}" \
  --environment-variables "file://${TMP_VARS_FILE}" >/dev/null

echo "Amplify branch environment variables updated."
