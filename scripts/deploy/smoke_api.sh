#!/usr/bin/env bash
set -euo pipefail

: "${API_BASE_URL:?API_BASE_URL is required (example: http://my-alb.us-east-1.elb.amazonaws.com)}"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required"
  exit 1
fi

BASE_URL="${API_BASE_URL%/}"
HEALTH_URL="${BASE_URL}/api/health/"

echo "Smoke check: ${HEALTH_URL}"
HEALTH_BODY="$(curl -fsS --connect-timeout 10 --max-time 20 "${HEALTH_URL}")"
echo "Health response: ${HEALTH_BODY}"

if [[ -n "${AUTH_TOKEN:-}" ]]; then
  ME_URL="${BASE_URL}/api/auth/users/me/"
  echo "Smoke check (authenticated): ${ME_URL}"
  curl -fsS \
    --connect-timeout 10 \
    --max-time 20 \
    -H "Authorization: Bearer ${AUTH_TOKEN}" \
    "${ME_URL}" >/dev/null
fi

echo "API smoke test passed."
