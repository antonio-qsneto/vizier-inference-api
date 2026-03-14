#!/usr/bin/env bash
set -euo pipefail

: "${API_BASE_URL:?API_BASE_URL is required (example: http://my-alb.us-east-1.elb.amazonaws.com)}"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required"
  exit 1
fi

BASE_URL="${API_BASE_URL%/}"
HEALTH_URL="${BASE_URL}/api/health/"
SMOKE_MAX_ATTEMPTS="${SMOKE_MAX_ATTEMPTS:-30}"
SMOKE_SLEEP_SECONDS="${SMOKE_SLEEP_SECONDS:-10}"
TMP_BODY_FILE="$(mktemp)"
LAST_HTTP_CODE=""

echo "Smoke check: ${HEALTH_URL}"
for attempt in $(seq 1 "${SMOKE_MAX_ATTEMPTS}"); do
  LAST_HTTP_CODE="$(curl -sS \
    --connect-timeout 10 \
    --max-time 20 \
    -o "${TMP_BODY_FILE}" \
    -w "%{http_code}" \
    "${HEALTH_URL}" || true)"

  if [[ "${LAST_HTTP_CODE}" == "200" ]]; then
    echo "Health response: $(cat "${TMP_BODY_FILE}")"
    break
  fi

  if [[ "${attempt}" -lt "${SMOKE_MAX_ATTEMPTS}" ]]; then
    echo "Attempt ${attempt}/${SMOKE_MAX_ATTEMPTS} returned HTTP ${LAST_HTTP_CODE}. Retrying in ${SMOKE_SLEEP_SECONDS}s..."
    sleep "${SMOKE_SLEEP_SECONDS}"
  fi
done

if [[ "${LAST_HTTP_CODE}" != "200" ]]; then
  echo "Health check failed after ${SMOKE_MAX_ATTEMPTS} attempts. Last HTTP: ${LAST_HTTP_CODE}"
  echo "Last response body:"
  cat "${TMP_BODY_FILE}" || true
  exit 1
fi

if [[ -n "${AUTH_TOKEN:-}" ]]; then
  ME_URL="${BASE_URL}/api/auth/users/me/"
  echo "Smoke check (authenticated): ${ME_URL}"
  curl -fsS \
    --connect-timeout 10 \
    --max-time 20 \
    -H "Authorization: Bearer ${AUTH_TOKEN}" \
    "${ME_URL}" >/dev/null
fi

rm -f "${TMP_BODY_FILE}"
echo "API smoke test passed."
