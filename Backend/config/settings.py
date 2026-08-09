import os
from config.environment import load_project_environment
from config.runtime_validation import resolve_jwt_secret, validate_seed_settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_project_environment(BASE_DIR)

DATA_DIR = os.environ.get("PMS_DATA_DIR", os.path.join(BASE_DIR, "data"))

DEFAULT_FILE_PATH = os.environ.get("PMS_DEFAULT_FILE_PATH", r"D:\Trend\PMS_Trend_All.xlsx")
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
PORT = int(os.environ.get("PORT", "8000"))
PMS_AUTO_SEED = os.environ.get(
    "PMS_AUTO_SEED",
    "true" if APP_ENV == "development" else "false",
).strip().lower() == "true"
PMS_SEED_PERMISSIONS_ON_STARTUP = os.environ.get(
    "PMS_SEED_PERMISSIONS_ON_STARTUP",
    "true" if APP_ENV == "development" else "false",
).strip().lower() == "true"
PMS_SEED_DEMO_LEVELS = os.environ.get("PMS_SEED_DEMO_LEVELS", "false").strip().lower() == "true"

validate_seed_settings(
    APP_ENV,
    {
        "PMS_AUTO_SEED": PMS_AUTO_SEED,
        "PMS_SEED_PERMISSIONS_ON_STARTUP": PMS_SEED_PERMISSIONS_ON_STARTUP,
        "PMS_SEED_DEMO_LEVELS": PMS_SEED_DEMO_LEVELS,
    },
)

# Comma-separated list of allowed origins. Do not use wildcards in production with credentials.
def parse_cors_origins(value: str) -> tuple[str, ...]:
    return tuple(origin.strip().rstrip('/') for origin in value.split(",") if origin.strip())


_cors_origins = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,https://pms-frontend-iota-dusky.vercel.app",
)
CORS_ORIGINS = parse_cors_origins(_cors_origins)
if APP_ENV == "production" and "*" in CORS_ORIGINS:
    raise ValueError("CORS_ALLOWED_ORIGINS must contain explicit origins when credentials are enabled in production.")

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
if MAX_UPLOAD_BYTES <= 0:
    raise ValueError("MAX_UPLOAD_BYTES must be greater than zero.")

# Security Roles definitions
ROLE_ADMIN = "Admin"
ROLE_MANAGER = "Manager"
ROLE_EXECUTIVE = "Executive"
ROLE_VIEWER = "Viewer"

ROLES = [ROLE_ADMIN, ROLE_MANAGER, ROLE_EXECUTIVE, ROLE_VIEWER]

# JWT & Security settings
JWT_SECRET = resolve_jwt_secret(os.environ.get("JWT_SECRET"), APP_ENV)
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

# Redis settings
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_SOCKET_TIMEOUT_SECONDS = float(os.environ.get("REDIS_SOCKET_TIMEOUT_SECONDS", "0.25"))
REDIS_RETRY_INTERVAL_SECONDS = float(os.environ.get("REDIS_RETRY_INTERVAL_SECONDS", "30"))
if REDIS_SOCKET_TIMEOUT_SECONDS <= 0:
    raise ValueError("REDIS_SOCKET_TIMEOUT_SECONDS must be greater than zero.")
if REDIS_RETRY_INTERVAL_SECONDS < 0:
    raise ValueError("REDIS_RETRY_INTERVAL_SECONDS cannot be negative.")

# Socket.IO presence is process-local. Disable it by default on serverless hosts.
PMS_REALTIME_MODE = os.environ.get(
    "PMS_REALTIME_MODE",
    "disabled" if os.environ.get("VERCEL") else "in_process",
).strip().lower()
if PMS_REALTIME_MODE not in {"disabled", "in_process"}:
    raise ValueError("PMS_REALTIME_MODE must be either 'disabled' or 'in_process'.")


class _SettingsCompatibility:
    """Attribute-style access retained for existing runtime/tests callers."""

    MAX_UPLOAD_BYTES = MAX_UPLOAD_BYTES


settings = _SettingsCompatibility()

