import os
from config.environment import load_project_environment
from config.runtime_validation import resolve_jwt_secret, validate_seed_settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_project_environment(BASE_DIR)

DATA_DIR = os.environ.get("PMS_DATA_DIR", os.path.join(BASE_DIR, "data"))
PMS_DATA_DIR = DATA_DIR

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
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:3000,https://pms-frontend-iota-dusky.vercel.app",
)
CORS_ORIGINS = parse_cors_origins(_cors_origins)
if APP_ENV == "production" and "*" in CORS_ORIGINS:
    raise ValueError("CORS_ALLOWED_ORIGINS must contain explicit origins when credentials are enabled in production.")

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
if MAX_UPLOAD_BYTES <= 0:
    raise ValueError("MAX_UPLOAD_BYTES must be greater than zero.")


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Heavy upload/report work is opt-in outside the worker-enabled deployment.
# This keeps local and compatibility environments on the existing synchronous
# contract until the migration and worker are explicitly enabled.
PMS_ASYNC_JOBS_ENABLED = parse_bool(
    os.environ.get("PMS_ASYNC_JOBS_ENABLED"),
    default=False,
)
PMS_JOB_DATA_DIR = os.environ.get("PMS_JOB_DATA_DIR", os.path.join(DATA_DIR, "jobs"))
PMS_JOB_POLL_SECONDS = float(os.environ.get("PMS_JOB_POLL_SECONDS", "1.0"))
PMS_JOB_LEASE_SECONDS = int(os.environ.get("PMS_JOB_LEASE_SECONDS", "300"))
PMS_JOB_MAX_ATTEMPTS = int(os.environ.get("PMS_JOB_MAX_ATTEMPTS", "3"))
PMS_JOB_FAILED_FILE_RETENTION_SECONDS = int(
    os.environ.get("PMS_JOB_FAILED_FILE_RETENTION_SECONDS", str(24 * 60 * 60))
)
PMS_SCOPED_PERFORMANCE_API_ENABLED = parse_bool(
    os.environ.get("PMS_SCOPED_PERFORMANCE_API_ENABLED"),
    default=False,
)
PMS_SCOPED_PERFORMANCE_ALLOWED_ROLES = tuple(
    role.strip()
    for role in os.environ.get("PMS_SCOPED_PERFORMANCE_ALLOWED_ROLES", "").split(",")
    if role.strip()
)
PMS_REPORT_CENTER_ENABLED = parse_bool(
    os.environ.get("PMS_REPORT_CENTER_ENABLED"),
    default=True,
)
if PMS_JOB_POLL_SECONDS <= 0:
    raise ValueError("PMS_JOB_POLL_SECONDS must be greater than zero.")
if PMS_JOB_LEASE_SECONDS <= 0:
    raise ValueError("PMS_JOB_LEASE_SECONDS must be greater than zero.")
if PMS_JOB_MAX_ATTEMPTS <= 0:
    raise ValueError("PMS_JOB_MAX_ATTEMPTS must be greater than zero.")

# Security Roles definitions
ROLE_ADMIN = "Admin"
ROLE_MANAGER = "Manager"
ROLE_EXECUTIVE = "Executive"
ROLE_VIEWER = "Viewer"

ROLES = [ROLE_ADMIN, ROLE_MANAGER, ROLE_EXECUTIVE, ROLE_VIEWER]

# JWT & Security settings
JWT_SECRET = resolve_jwt_secret(os.environ.get("JWT_SECRET"), APP_ENV)
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "10"))
AUTH_REFRESH_COOKIE_NAME = os.environ.get("AUTH_REFRESH_COOKIE_NAME", "pms_refresh_token")
AUTH_CSRF_COOKIE_NAME = os.environ.get("AUTH_CSRF_COOKIE_NAME", "pms_csrf_token")
AUTH_REFRESH_SESSION_HOURS = int(os.environ.get("AUTH_REFRESH_SESSION_HOURS", "8"))
AUTH_REMEMBER_SESSION_DAYS = int(os.environ.get("AUTH_REMEMBER_SESSION_DAYS", "30"))
AUTH_COOKIE_SECURE = parse_bool(
    os.environ.get("AUTH_COOKIE_SECURE"),
    default=APP_ENV in {"production", "staging"},
)
AUTH_COOKIE_SAMESITE = os.environ.get(
    "AUTH_COOKIE_SAMESITE",
    "none" if APP_ENV in {"production", "staging"} else "lax",
).strip().lower()
AUTH_COOKIE_DOMAIN = os.environ.get("AUTH_COOKIE_DOMAIN", "").strip() or None
if AUTH_COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise ValueError("AUTH_COOKIE_SAMESITE must be lax, strict, or none.")
if AUTH_COOKIE_SAMESITE == "none" and not AUTH_COOKIE_SECURE:
    raise ValueError("AUTH_COOKIE_SECURE must be enabled when AUTH_COOKIE_SAMESITE=none.")
if JWT_EXPIRE_MINUTES <= 0:
    raise ValueError("JWT_EXPIRE_MINUTES must be greater than zero.")
if AUTH_REFRESH_SESSION_HOURS <= 0:
    raise ValueError("AUTH_REFRESH_SESSION_HOURS must be greater than zero.")
if AUTH_REMEMBER_SESSION_DAYS <= 0:
    raise ValueError("AUTH_REMEMBER_SESSION_DAYS must be greater than zero.")

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
    PMS_ASYNC_JOBS_ENABLED = PMS_ASYNC_JOBS_ENABLED
    PMS_DATA_DIR = DATA_DIR
    PMS_JOB_DATA_DIR = PMS_JOB_DATA_DIR
    PMS_JOB_POLL_SECONDS = PMS_JOB_POLL_SECONDS
    PMS_JOB_LEASE_SECONDS = PMS_JOB_LEASE_SECONDS
    PMS_JOB_MAX_ATTEMPTS = PMS_JOB_MAX_ATTEMPTS
    PMS_JOB_FAILED_FILE_RETENTION_SECONDS = PMS_JOB_FAILED_FILE_RETENTION_SECONDS
    PMS_SCOPED_PERFORMANCE_API_ENABLED = PMS_SCOPED_PERFORMANCE_API_ENABLED
    PMS_SCOPED_PERFORMANCE_ALLOWED_ROLES = PMS_SCOPED_PERFORMANCE_ALLOWED_ROLES
    PMS_REPORT_CENTER_ENABLED = PMS_REPORT_CENTER_ENABLED
    JWT_EXPIRE_MINUTES = JWT_EXPIRE_MINUTES
    AUTH_REFRESH_COOKIE_NAME = AUTH_REFRESH_COOKIE_NAME
    AUTH_CSRF_COOKIE_NAME = AUTH_CSRF_COOKIE_NAME
    AUTH_REFRESH_SESSION_HOURS = AUTH_REFRESH_SESSION_HOURS
    AUTH_REMEMBER_SESSION_DAYS = AUTH_REMEMBER_SESSION_DAYS
    AUTH_COOKIE_SECURE = AUTH_COOKIE_SECURE
    AUTH_COOKIE_SAMESITE = AUTH_COOKIE_SAMESITE
    AUTH_COOKIE_DOMAIN = AUTH_COOKIE_DOMAIN


settings = _SettingsCompatibility()

