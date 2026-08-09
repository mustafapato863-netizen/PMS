#!/bin/bash
# ==============================================================================
# Health Check Verification Script
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${PMS_ENV_FILE:-${PROJECT_ROOT}/DevOps/.env.hostinger}"

ENV_DOMAIN=""
if [ -f "${ENV_FILE}" ]; then
  ENV_DOMAIN="$(sed -n 's/^APP_DOMAIN=//p' "${ENV_FILE}" | head -n 1 | tr -d '\r')"
  ENV_DOMAIN="${ENV_DOMAIN%\"}"
  ENV_DOMAIN="${ENV_DOMAIN#\"}"
fi

if [ -n "${HEALTHCHECK_URL:-}" ]; then
  ENDPOINT="${HEALTHCHECK_URL}"
elif [ -n "${APP_DOMAIN:-${ENV_DOMAIN}}" ]; then
  ENDPOINT="https://${APP_DOMAIN:-${ENV_DOMAIN}}/api/health/readiness"
else
  ENDPOINT="http://127.0.0.1/api/health/readiness"
fi

echo "[INFO] Querying system readiness check endpoint: ${ENDPOINT}..."

# Wait and query for up to 90 seconds.
for i in {1..18}; do
  # Use curl with silent output and HTTP status assertion
  if curl -s -f "${ENDPOINT}" > /dev/null; then
    echo "[SUCCESS] System is healthy and ready to receive traffic."
    exit 0
  else
    echo "[INFO] Service is bootstrapping. Retrying in 5 seconds (attempt $i/18)..."
    sleep 5
  fi
done

echo "[ERROR] Readiness check failed. Service returned unhealthy state or is unreachable."
exit 1
