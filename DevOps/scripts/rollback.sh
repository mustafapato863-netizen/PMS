#!/bin/bash
# ==============================================================================
# Deployment Rollback Script
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/compose.production.yml"
ENV_FILE="${PMS_ENV_FILE:-${PROJECT_ROOT}/DevOps/.env.hostinger}"
cd "${PROJECT_ROOT}"

if [ ! -f "${ENV_FILE}" ]; then
  echo "[ERROR] Missing deployment environment file: ${ENV_FILE}"
  exit 1
fi

if [ -z "${PREVIOUS_APP_VERSION:-}" ]; then
  echo "[ERROR] Set PREVIOUS_APP_VERSION to the last known-good commit SHA or image tag."
  exit 1
fi

echo "[WARNING] This will redeploy application images tagged ${PREVIOUS_APP_VERSION}."
echo "[WARNING] Database migrations will not be downgraded automatically."
read -r -p "Continue with the application rollback? (y/N) " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
  echo "[INFO] Rollback procedure cancelled by user."
  exit 0
fi

echo "[INFO] Starting the already-built previous application images without running a database downgrade or old migration job..."
export APP_VERSION="${PREVIOUS_APP_VERSION}"
if docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --no-build redis && \
   docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --no-build --no-deps backend frontend && \
   docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --no-build --no-deps gateway; then
  PMS_ENV_FILE="${ENV_FILE}" "${SCRIPT_DIR}/health-check.sh"
  echo "[SUCCESS] Previous application release is healthy."
else
  echo "[ERROR] Failed to start the previous application release. Confirm that both previous images still exist on the VPS."
  exit 1
fi
