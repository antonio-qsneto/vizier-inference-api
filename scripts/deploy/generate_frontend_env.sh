#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Generate frontend VITE env values from Terraform outputs.

Usage:
  ./scripts/deploy/generate_frontend_env.sh [options]

Options:
  --env <dev|prod>               Terraform environment (default: dev)
  --output <path>                Output file path (default: frontend/.env.generated.<env>.txt)
  --frontend-base-url <url>      Frontend base URL (default: http://localhost:3000)
  --api-scheme <http|https>      API scheme for ALB URL (default: http)
  --async-upload <true|false>    Value for VITE_USE_ASYNC_S3_UPLOAD (default: true)
  --redirect-uri <url>           Override VITE_COGNITO_REDIRECT_URI
  --logout-uri <url>             Override VITE_COGNITO_LOGOUT_URI
  --help                         Show this help

Examples:
  ./scripts/deploy/generate_frontend_env.sh
  ./scripts/deploy/generate_frontend_env.sh --env dev --frontend-base-url https://main.d123.amplifyapp.com
EOF
}

ENVIRONMENT="dev"
OUTPUT_FILE=""
FRONTEND_BASE_URL="http://localhost:3000"
API_SCHEME="http"
ASYNC_UPLOAD="true"
REDIRECT_URI=""
LOGOUT_URI=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENVIRONMENT="${2:-}"
      shift 2
      ;;
    --output)
      OUTPUT_FILE="${2:-}"
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
    --redirect-uri)
      REDIRECT_URI="${2:-}"
      shift 2
      ;;
    --logout-uri)
      LOGOUT_URI="${2:-}"
      shift 2
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

if [[ "${API_SCHEME}" != "http" && "${API_SCHEME}" != "https" ]]; then
  echo "--api-scheme must be http or https"
  exit 1
fi

if [[ "${FRONTEND_BASE_URL}" == https://* && "${API_SCHEME}" == "http" ]]; then
  cat <<'EOF' >&2
WARNING: frontend-base-url is HTTPS but API scheme is HTTP.
Browsers will block API calls from the frontend due to mixed content.
Use --api-scheme https once your backend endpoint supports TLS.
EOF
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TF_ENV_DIR="${REPO_ROOT}/vizier-inference-infra/terraform/envs/${ENVIRONMENT}"
BACKEND_HCL="${TF_ENV_DIR}/backend.hcl"

if [[ ! -f "${BACKEND_HCL}" ]]; then
  echo "Terraform backend config not found: ${BACKEND_HCL}"
  echo "Create it first (see DEPLOY_AWS_FROM_SCRATCH.md)."
  exit 1
fi

if [[ -z "${OUTPUT_FILE}" ]]; then
  OUTPUT_FILE="${REPO_ROOT}/frontend/.env.generated.${ENVIRONMENT}.txt"
fi

if ! command -v terraform >/dev/null 2>&1; then
  echo "terraform is required"
  exit 1
fi

terraform -chdir="${TF_ENV_DIR}" init -input=false -reconfigure -backend-config=backend.hcl >/dev/null

REGION="$(terraform -chdir="${TF_ENV_DIR}" output -raw region)"
ALB_DNS_NAME="$(terraform -chdir="${TF_ENV_DIR}" output -raw alb_dns_name)"
COGNITO_USER_POOL_ID="$(terraform -chdir="${TF_ENV_DIR}" output -raw cognito_user_pool_id)"
COGNITO_CLIENT_ID="$(terraform -chdir="${TF_ENV_DIR}" output -raw cognito_user_pool_client_id)"
COGNITO_DOMAIN_PREFIX="$(terraform -chdir="${TF_ENV_DIR}" output -raw cognito_user_pool_domain)"

COGNITO_DOMAIN="https://${COGNITO_DOMAIN_PREFIX}.auth.${REGION}.amazoncognito.com"
DEFAULT_REDIRECT_URI="${FRONTEND_BASE_URL%/}/auth/callback"
DEFAULT_LOGOUT_URI="${FRONTEND_BASE_URL%/}/login"

if [[ -z "${REDIRECT_URI}" ]]; then
  REDIRECT_URI="${DEFAULT_REDIRECT_URI}"
fi

if [[ -z "${LOGOUT_URI}" ]]; then
  LOGOUT_URI="${DEFAULT_LOGOUT_URI}"
fi

mkdir -p "$(dirname "${OUTPUT_FILE}")"

cat >"${OUTPUT_FILE}" <<EOF
VITE_API_BASE_URL=${API_SCHEME}://${ALB_DNS_NAME}
VITE_USE_ASYNC_S3_UPLOAD=${ASYNC_UPLOAD}
VITE_COGNITO_REGION=${REGION}
VITE_COGNITO_USER_POOL_ID=${COGNITO_USER_POOL_ID}
VITE_COGNITO_CLIENT_ID=${COGNITO_CLIENT_ID}
VITE_COGNITO_DOMAIN=${COGNITO_DOMAIN}
VITE_COGNITO_REDIRECT_URI=${REDIRECT_URI}
VITE_COGNITO_LOGOUT_URI=${LOGOUT_URI}
EOF

echo "Generated: ${OUTPUT_FILE}"
cat "${OUTPUT_FILE}"
