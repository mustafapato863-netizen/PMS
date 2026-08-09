#!/bin/bash
# ==============================================================================
# Database Migrations Script
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

echo "[INFO] Executing database migrations to the latest head revision..."

if docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" run --rm migrate; then
  echo "[SUCCESS] Schema migrations applied successfully."
else
  echo "[ERROR] Schema migrations failed to execute."
  exit 1
fi
