import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config.environment import load_project_environment
from config.runtime_validation import resolve_database_url

# Load the shared DevOps environment file from the repository root.
# Local overrides take precedence over default environment settings.
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_project_environment(backend_dir)

# Development/test may use the local fallback. Production must provide PostgreSQL.
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
DATABASE_URL = resolve_database_url(
    os.getenv("DATABASE_URL"),
    APP_ENV,
    logger=logging.getLogger(__name__),
)

def _int_setting(name: str, default: int, *, minimum: int = 0) -> int:
    """Optional integer env setting; invalid or out-of-range values fall back to the default."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        logging.getLogger(__name__).warning("Ignoring invalid %s=%r; using %s", name, raw, default)
        return default
    return value if value >= minimum else default


def _bool_setting(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Pool sizing. All settings are optional; the defaults apply when unset.
# Production previously ran 5 + 0 overflow with a 30s wait, which hung the API
# when every connection was busy. The new defaults leave burst headroom (15
# connections total) and fail fast (10s) instead of queueing requests for 30s.
# Keep pool_size + max_overflow (per worker process) under the database or
# pooler connection limit.
is_development = APP_ENV == "development"
pool_size = _int_setting("DATABASE_POOL_SIZE", 20 if is_development else 10, minimum=1)
max_overflow = _int_setting("DATABASE_MAX_OVERFLOW", 10 if is_development else 5)
pool_timeout = _int_setting("DATABASE_POOL_TIMEOUT", 10, minimum=1)
pool_recycle = _int_setting("DATABASE_POOL_RECYCLE", 1800, minimum=-1)
pool_pre_ping = _bool_setting("DATABASE_POOL_PRE_PING", True)
# Server-side safety net (PostgreSQL only): a session left idle inside an open
# transaction is terminated by the server after this many milliseconds, so a
# leaked transaction can never pin a pool connection (or row locks) forever.
# 0 disables it. Requests never sit idle-in-transaction this long legitimately.
idle_in_transaction_timeout_ms = _int_setting("DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS", 60_000)


def postgres_connect_args(url: str, timeout_ms: int) -> dict:
    """connect_args for libpq-based drivers (psycopg2 / psycopg 3)."""
    lowered = url.lower()
    if timeout_ms <= 0 or not lowered.startswith("postgres") or "asyncpg" in lowered or "options=" in lowered:
        return {}
    return {"options": f"-c idle_in_transaction_session_timeout={int(timeout_ms)}"}


engine_kwargs = {
    "pool_pre_ping": pool_pre_ping,
}
if "sqlite" not in DATABASE_URL.lower():
    engine_kwargs.update({
        "pool_size": pool_size,
        "max_overflow": max_overflow,
        "pool_timeout": pool_timeout,
        "pool_recycle": pool_recycle,
    })
    pg_connect_args = postgres_connect_args(DATABASE_URL, idle_in_transaction_timeout_ms)
    if pg_connect_args:
        engine_kwargs["connect_args"] = pg_connect_args
else:
    engine_kwargs.update({
        "connect_args": {"check_same_thread": False}
    })

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Request-scoped session: always closed (and its connection returned) in finally."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def release_read_transaction(db) -> None:
    """End a read-only request's transaction before the response is serialized.

    ``Depends(get_db)`` tears down only after the response has been sent, so a
    handler that only read would otherwise keep its pooled connection "idle in
    transaction" for the whole serialization and network send. Read endpoints
    call this right before returning; any later lazy load simply starts a new,
    short transaction that get_db closes.
    """
    in_transaction = getattr(db, "in_transaction", None)
    if callable(in_transaction) and in_transaction():
        db.rollback()

