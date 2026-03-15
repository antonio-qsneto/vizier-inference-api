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
                                If omitted, tries custom domain for branch, then branch.webUrl.
  --api-scheme <http|https>     Scheme for VITE_API_BASE_URL (default: http)
  --api-base-url <url>          Explicit VITE_API_BASE_URL override
  --enable-api-proxy            Force Amplify reverse-proxy rule /api/<*> -> ALB
  --disable-api-proxy           Disable Amplify reverse-proxy rule automation
  --async-upload <true|false>   Value for VITE_USE_ASYNC_S3_UPLOAD (default: true)
  --keep-app-level-vite-vars    Keep managed VITE_* vars at Amplify app level
                                (default behavior is to remove them to avoid duplicates)
  --dry-run                     Print merged variables without applying
  --help                        Show this help

Examples:
  ./scripts/deploy/sync_amplify_env.sh --env dev --app-id d2fezrl1u8wfmh --frontend-base-url https://viziermed.com
  ./scripts/deploy/sync_amplify_env.sh --env prod --app-id d2fezrl1u8wfmh --api-scheme https --frontend-base-url https://viziermed.com
EOF
}

ENVIRONMENT="dev"
APP_ID="${AMPLIFY_APP_ID:-}"
BRANCH="main"
FRONTEND_BASE_URL=""
API_SCHEME="http"
API_BASE_URL_OVERRIDE=""
ASYNC_UPLOAD="true"
DRY_RUN="false"
KEEP_APP_LEVEL_VITE_VARS="false"
ENABLE_API_PROXY="auto"

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
    --api-base-url)
      API_BASE_URL_OVERRIDE="${2:-}"
      shift 2
      ;;
    --enable-api-proxy)
      ENABLE_API_PROXY="true"
      shift
      ;;
    --disable-api-proxy)
      ENABLE_API_PROXY="false"
      shift
      ;;
    --async-upload)
      ASYNC_UPLOAD="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    --keep-app-level-vite-vars)
      KEEP_APP_LEVEL_VITE_VARS="true"
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
API_CLOUDFRONT_DOMAIN="$(terraform -chdir="${TF_ENV_DIR}" output -raw api_cloudfront_domain_name 2>/dev/null || true)"
COGNITO_USER_POOL_ID="$(terraform -chdir="${TF_ENV_DIR}" output -raw cognito_user_pool_id)"
COGNITO_CLIENT_ID="$(terraform -chdir="${TF_ENV_DIR}" output -raw cognito_user_pool_client_id)"
COGNITO_DOMAIN_PREFIX="$(terraform -chdir="${TF_ENV_DIR}" output -raw cognito_user_pool_domain)"

if [[ -z "${FRONTEND_BASE_URL}" ]]; then
  CUSTOM_FRONTEND_URL="$(aws amplify list-domain-associations \
    --app-id "${APP_ID}" \
    --query 'domainAssociations' \
    --output json 2>/dev/null \
    | jq -r --arg branch "${BRANCH}" '
      (if type == "array" then . else [] end)
      | map(
          . as $domain
          | (.subDomains // [])[]
          | select((.subDomainSetting.branchName // "") == $branch)
          | {
              domain: ($domain.domainName // ""),
              prefix: (.subDomainSetting.prefix // "")
            }
        )
      | map(select(.domain != ""))
      | sort_by(if .prefix == "" then 0 else 1 end)
      | .[0] as $selected
      | if $selected == null then
          empty
        elif ($selected.prefix | length) == 0 then
          "https://\($selected.domain)"
        else
          "https://\($selected.prefix).\($selected.domain)"
        end
    ' || true)"

  if [[ -n "${CUSTOM_FRONTEND_URL}" && "${CUSTOM_FRONTEND_URL}" != "null" && "${CUSTOM_FRONTEND_URL}" != "None" ]]; then
    FRONTEND_BASE_URL="${CUSTOM_FRONTEND_URL}"
  else
    FRONTEND_BASE_URL="$(aws amplify get-branch \
      --app-id "${APP_ID}" \
      --branch-name "${BRANCH}" \
      --query 'branch.webUrl' \
      --output text 2>/dev/null || true)"
  fi
fi

if [[ -z "${FRONTEND_BASE_URL}" || "${FRONTEND_BASE_URL}" == "None" || "${FRONTEND_BASE_URL}" == "null" ]]; then
  echo "Could not resolve frontend base URL. Use --frontend-base-url."
  exit 1
fi

FRONTEND_BASE_URL="${FRONTEND_BASE_URL%/}"
REDIRECT_URI="${FRONTEND_BASE_URL}/auth/callback"
LOGOUT_URI="${FRONTEND_BASE_URL}/login"
COGNITO_DOMAIN="https://${COGNITO_DOMAIN_PREFIX}.auth.${REGION}.amazoncognito.com"
BACKEND_API_ORIGIN="${API_SCHEME}://${ALB_DNS_NAME}"
BACKEND_API_HTTPS_EDGE=""
if [[ -n "${API_CLOUDFRONT_DOMAIN}" && "${API_CLOUDFRONT_DOMAIN}" != "null" && "${API_CLOUDFRONT_DOMAIN}" != "None" ]]; then
  BACKEND_API_HTTPS_EDGE="https://${API_CLOUDFRONT_DOMAIN}"
fi

if [[ -n "${API_BASE_URL_OVERRIDE}" ]]; then
  API_BASE_URL="${API_BASE_URL_OVERRIDE%/}"
else
  API_BASE_URL="${BACKEND_API_ORIGIN}"
fi

if [[ "${ENABLE_API_PROXY}" == "auto" ]]; then
  if [[ "${FRONTEND_BASE_URL}" == https://* && "${API_SCHEME}" == "http" ]]; then
    if [[ -n "${BACKEND_API_HTTPS_EDGE}" ]]; then
      ENABLE_API_PROXY="false"
      if [[ -z "${API_BASE_URL_OVERRIDE}" ]]; then
        API_BASE_URL="${BACKEND_API_HTTPS_EDGE}"
      fi
    else
      ENABLE_API_PROXY="true"
      if [[ -z "${API_BASE_URL_OVERRIDE}" ]]; then
        API_BASE_URL="${FRONTEND_BASE_URL}"
      fi
    fi
  else
    ENABLE_API_PROXY="false"
  fi
fi

BILLING_CHECKOUT_ENDPOINT="${API_BASE_URL}/api/auth/billing/checkout/"
BILLING_PORTAL_ENDPOINT="${API_BASE_URL}/api/auth/billing/portal/"

NEW_VARS_JSON="$(jq -n \
  --arg api_base_url "${API_BASE_URL}" \
  --arg billing_checkout_endpoint "${BILLING_CHECKOUT_ENDPOINT}" \
  --arg billing_portal_endpoint "${BILLING_PORTAL_ENDPOINT}" \
  --arg async_upload "${ASYNC_UPLOAD}" \
  --arg cognito_region "${REGION}" \
  --arg cognito_user_pool_id "${COGNITO_USER_POOL_ID}" \
  --arg cognito_client_id "${COGNITO_CLIENT_ID}" \
  --arg cognito_domain "${COGNITO_DOMAIN}" \
  --arg redirect_uri "${REDIRECT_URI}" \
  --arg logout_uri "${LOGOUT_URI}" \
  '{
    VITE_API_BASE_URL: $api_base_url,
    VITE_BILLING_CHECKOUT_ENDPOINT: $billing_checkout_endpoint,
    VITE_BILLING_PORTAL_ENDPOINT: $billing_portal_endpoint,
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

MANAGED_KEYS_JSON='[
  "VITE_API_BASE_URL",
  "VITE_BILLING_CHECKOUT_ENDPOINT",
  "VITE_BILLING_PORTAL_ENDPOINT",
  "VITE_USE_ASYNC_S3_UPLOAD",
  "VITE_COGNITO_REGION",
  "VITE_COGNITO_USER_POOL_ID",
  "VITE_COGNITO_CLIENT_ID",
  "VITE_COGNITO_DOMAIN",
  "VITE_COGNITO_REDIRECT_URI",
  "VITE_COGNITO_LOGOUT_URI"
]'

APP_VARS_JSON="$(aws amplify get-app \
  --app-id "${APP_ID}" \
  --query 'app.environmentVariables' \
  --output json 2>/dev/null || echo '{}')"

if [[ -z "${APP_VARS_JSON}" || "${APP_VARS_JSON}" == "null" ]]; then
  APP_VARS_JSON='{}'
fi

CLEAN_APP_VARS_JSON="$(jq --argjson keys "${MANAGED_KEYS_JSON}" '
  reduce $keys[] as $k (. ; del(.[$k]))
' <<< "${APP_VARS_JSON}")"

echo "Amplify app: ${APP_ID}"
echo "Amplify branch: ${BRANCH}"
echo "Frontend base URL: ${FRONTEND_BASE_URL}"
echo "Backend API origin: ${BACKEND_API_ORIGIN}"
if [[ -n "${BACKEND_API_HTTPS_EDGE}" ]]; then
  echo "Backend API HTTPS edge: ${BACKEND_API_HTTPS_EDGE}"
fi
echo "VITE_API_BASE_URL: ${API_BASE_URL}"
echo "VITE_BILLING_CHECKOUT_ENDPOINT: ${BILLING_CHECKOUT_ENDPOINT}"
echo "VITE_BILLING_PORTAL_ENDPOINT: ${BILLING_PORTAL_ENDPOINT}"
echo "Amplify API proxy automation: ${ENABLE_API_PROXY}"
echo "Merged VITE vars to apply:"
echo "${MERGED_VARS_JSON}" | jq '.'
if [[ "${KEEP_APP_LEVEL_VITE_VARS}" != "true" ]]; then
  echo "App-level VITE_* cleanup enabled (prevents duplicated keys in Amplify UI)."
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "Dry-run mode enabled. No changes applied."
  exit 0
fi

if [[ "${ENABLE_API_PROXY}" == "true" && "${BACKEND_API_ORIGIN}" == http://* ]]; then
  cat <<EOF
Amplify custom rules do not accept HTTP targets.
Current API origin is ${BACKEND_API_ORIGIN}.

Options:
1) Run terraform apply to provision api_cloudfront (HTTPS edge), then rerun this script.
2) Rerun with --disable-api-proxy and --api-base-url https://<your-https-api-endpoint>.
EOF
  exit 1
fi

TMP_VARS_FILE="$(mktemp)"
TMP_APP_VARS_FILE="$(mktemp)"
TMP_CUSTOM_RULES_FILE="$(mktemp)"
trap 'rm -f "${TMP_VARS_FILE}" "${TMP_APP_VARS_FILE}" "${TMP_CUSTOM_RULES_FILE}"' EXIT
echo "${MERGED_VARS_JSON}" > "${TMP_VARS_FILE}"

if [[ "${KEEP_APP_LEVEL_VITE_VARS}" != "true" ]]; then
  if [[ "${CLEAN_APP_VARS_JSON}" != "${APP_VARS_JSON}" ]]; then
    echo "${CLEAN_APP_VARS_JSON}" > "${TMP_APP_VARS_FILE}"
    aws amplify update-app \
      --app-id "${APP_ID}" \
      --environment-variables "file://${TMP_APP_VARS_FILE}" >/dev/null
    echo "Amplify app-level managed VITE vars removed."
  fi
fi

EXISTING_CUSTOM_RULES_JSON="$(aws amplify get-app \
  --app-id "${APP_ID}" \
  --query 'app.customRules' \
  --output json 2>/dev/null || echo '[]')"

if [[ -z "${EXISTING_CUSTOM_RULES_JSON}" || "${EXISTING_CUSTOM_RULES_JSON}" == "null" ]]; then
  EXISTING_CUSTOM_RULES_JSON='[]'
fi

SPA_SOURCE_REGEX='</^[^.]+$|\.(?!(css|gif|ico|jpg|jpeg|js|png|txt|svg|woff|woff2|ttf|map|json|webp)$)([^.]+$)/>'

if [[ "${ENABLE_API_PROXY}" == "true" ]]; then
  UPDATED_CUSTOM_RULES_JSON="$(jq \
    --arg proxy_target "${BACKEND_API_ORIGIN}/api/<*>" \
    --arg spa_source "${SPA_SOURCE_REGEX}" \
    '
    (if type == "array" then . else [] end)
    | map(
        select(
          (.source // "") != "/api/<*>"
          and ((.target // "") != "/index.html" or (.status // "") != "200")
        )
      )
    | [{ source: "/api/<*>", target: $proxy_target, status: "200" }] + . + [{ source: $spa_source, target: "/index.html", status: "200" }]
    ' <<< "${EXISTING_CUSTOM_RULES_JSON}")"
else
  UPDATED_CUSTOM_RULES_JSON="$(jq \
    --arg spa_source "${SPA_SOURCE_REGEX}" \
    '
    (if type == "array" then . else [] end)
    | map(select((.target // "") != "/index.html" or (.status // "") != "200"))
    | . + [{ source: $spa_source, target: "/index.html", status: "200" }]
    ' <<< "${EXISTING_CUSTOM_RULES_JSON}")"
fi

if [[ "${UPDATED_CUSTOM_RULES_JSON}" != "${EXISTING_CUSTOM_RULES_JSON}" ]]; then
  echo "${UPDATED_CUSTOM_RULES_JSON}" > "${TMP_CUSTOM_RULES_FILE}"
  aws amplify update-app \
    --app-id "${APP_ID}" \
    --custom-rules "file://${TMP_CUSTOM_RULES_FILE}" >/dev/null
  if [[ "${ENABLE_API_PROXY}" == "true" ]]; then
    echo "Amplify custom rules updated: /api proxy + SPA fallback."
  else
    echo "Amplify custom rules updated: SPA fallback."
  fi
fi

aws amplify update-branch \
  --app-id "${APP_ID}" \
  --branch-name "${BRANCH}" \
  --environment-variables "file://${TMP_VARS_FILE}" >/dev/null

echo "Amplify branch environment variables updated."
