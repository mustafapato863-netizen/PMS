#!/bin/bash
# ==============================================================================
# Production Deployment Script
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/compose.production.yml"
ENV_FILE="${PMS_ENV_FILE:-${PROJECT_ROOT}/DevOps/.env.hostinger}"
cd "${PROJECT_ROOT}"

if [ ! -f "${ENV_FILE}" ]; then
  echo "[ERROR] Missing deployment environment file: ${ENV_FILE}"
  echo "[INFO] Copy DevOps/.env.hostinger.example and populate production values."
  exit 1
fi

echo "[INFO] Validating the production Compose project..."
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config --quiet

echo "[INFO] Building immutable frontend and backend images..."
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" build backend frontend migrate

echo "[INFO] Starting the production services; backend startup waits for migrations to complete..."
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --no-build --remove-orphans

echo "[INFO] Triggering post-deployment health checks..."
PMS_ENV_FILE="${ENV_FILE}" "${SCRIPT_DIR}/health-check.sh"

echo "[SUCCESS] Production deployment completed."
