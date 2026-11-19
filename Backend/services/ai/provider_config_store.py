"""Runtime AI provider configuration: database overrides over environment defaults.

One small, thread-safe, short-TTL cache keeps provider calls cheap while keeping
Admin edits effective immediately (the write endpoints invalidate the cache).

Fallback order for every field is: database row -> environment variable ->
built-in default. Any database error degrades silently to the environment, so
isolated unit tests and fresh deployments never require the new table.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from services.ai.secret_crypto import decrypt_secret

logger = logging.getLogger(__name__)

PROVIDERS: tuple[str, ...] = ("cloudflare", "gemini", "nvidia")
KEY_SLOTS: tuple[str, ...] = ("primary", "alternate")

CACHE_TTL_SECONDS = 5.0
DB_FAILURE_BACKOFF_SECONDS = 30.0

DEFAULT_CLOUDFLARE_MODEL = "@cf/ibm-granite/granite-4.0-h-micro"
DEFAULT_CLOUDFLARE_ALTER_MODEL = "@cf/zai-org/glm-4.7-flash"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_NVIDIA_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
DEFAULT_NVIDIA_DAILY_LIMIT = 50


def _env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _truthy(value: str | None, default: bool) -> tuple[bool, str]:
    if value is None or not str(value).strip():
        return default, "default"
    norm = str(value).strip().casefold()
    if norm in ("1", "true", "yes", "on", "enabled"):
        return True, "env"
    if norm in ("0", "false", "no", "off", "disabled"):
        return False, "env"
    return default, "default"


def _parse_daily_limit(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    """Effective, decrypted configuration for a single provider."""

    provider: str
    enabled: bool
    enabled_source: str
    primary_model: str
    alternate_model: str | None
    primary_model_source: str
    account_id: str
    alternate_account_id: str
    account_id_source: str
    alternate_account_id_source: str
    primary_api_key: str
    alternate_api_key: str
    primary_key_source: str
    alternate_key_source: str
    active_key_slot: str
    auto_failover_key: bool
    daily_limit: int | None
    updated_at: str | None = None

    @property
    def active_api_key(self) -> str:
        return self.alternate_api_key if self.active_key_slot == "alternate" else self.primary_api_key

    @property
    def standby_api_key(self) -> str:
        return self.primary_api_key if self.active_key_slot == "alternate" else self.alternate_api_key

    @property
    def active_account_id(self) -> str:
        if self.active_key_slot == "alternate" and self.alternate_account_id:
            return self.alternate_account_id
        return self.account_id

    @property
    def standby_account_id(self) -> str:
        if self.active_key_slot == "alternate":
            return self.account_id
        return self.alternate_account_id or self.account_id

    def slot_has_credentials(self, slot: str) -> bool:
        return bool(self.alternate_api_key if slot == "alternate" else self.primary_api_key)


def _env_defaults(provider: str) -> dict[str, Any]:
    if provider == "cloudflare":
        enabled, enabled_source = _truthy(os.environ.get("PMS_AI_CLOUDFLARE_ENABLED"), True)
        return {
            "enabled": enabled,
            "enabled_source": enabled_source,
            "primary_model": _env(
                "CLOUDFLARE_AI_MODEL",
                "CF_AI_MODEL",
                "PMS_CLOUDFLARE_MODEL",
            )
            or DEFAULT_CLOUDFLARE_MODEL,
            "alternate_model": _env(
                "CLOUDFLARE_AI_MODEL_ALTER",
                "CF_AI_MODEL_ALTER",
                "CLOUDFLARE_MODEL_ALTER",
            )
            or DEFAULT_CLOUDFLARE_ALTER_MODEL,
            "account_id": _env("CLOUDFLARE_ACCOUNT_ID", "CF_ACCOUNT_ID"),
            "alternate_account_id": _env("CLOUDFLARE_ACCOUNT_ID_ALTER", "CF_ACCOUNT_ID_ALTER"),
            "primary_api_key": _env("CLOUDFLARE_API_TOKEN", "CF_API_TOKEN", "CLOUDFLARE_API_KEY"),
            "alternate_api_key": _env(
                "CLOUDFLARE_API_TOKEN_ALTER",
                "CF_API_TOKEN_ALTER",
                "CLOUDFLARE_API_KEY_ALTER",
            ),
            "daily_limit": None,
        }
    if provider == "gemini":
        enabled, enabled_source = _truthy(os.environ.get("PMS_AI_GEMINI_ENABLED"), True)
        return {
            "enabled": enabled,
            "enabled_source": enabled_source,
            "primary_model": _env(
                "PMS_GEMINI_MODEL",
                "PMS_AI_GEMINI_MODEL",
                "GEMINI_MODEL",
            )
            or DEFAULT_GEMINI_MODEL,
            "alternate_model": None,
            "account_id": "",
            "alternate_account_id": "",
            "primary_api_key": _env("GEMINI_API_KEY", "Gemini_API_KEY", "GOOGLE_API_KEY"),
            "alternate_api_key": _env("GEMINI_API_KEY_ALTER", "GOOGLE_API_KEY_ALTER"),
            "daily_limit": None,
        }
    enabled, enabled_source = _truthy(
        os.environ.get("PMS_AI_FEEDBACK_ANALYZER_ENABLED"), False
    )
    daily_raw = os.environ.get(
        "PMS_AI_FEEDBACK_ANALYZER_DAILY_LIMIT", str(DEFAULT_NVIDIA_DAILY_LIMIT)
    )
    return {
        "enabled": enabled,
        "enabled_source": enabled_source,
        "primary_model": _env("NVIDIA_FEEDBACK_MODEL") or DEFAULT_NVIDIA_MODEL,
        "alternate_model": None,
        "account_id": "",
        "alternate_account_id": "",
        "primary_api_key": _env("NVIDIA_API_KEY"),
        "alternate_api_key": _env("NVIDIA_API_KEY_ALTER"),
        "daily_limit": _parse_daily_limit(daily_raw),
    }


_db_failure_until = 0.0


def _db_row(provider: str, db: Session | None) -> Any | None:
    global _db_failure_until
    own_session = False
    session = db
    if session is None:
        if time.monotonic() < _db_failure_until:
            return None
        try:
            from config.database import SessionLocal

            session = SessionLocal()
            own_session = True
        except Exception:
            return None
    try:
        from models.models import AiProviderConfig

        return session.query(AiProviderConfig).filter(AiProviderConfig.provider == provider).one_or_none()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        if own_session:
            _db_failure_until = time.monotonic() + DB_FAILURE_BACKOFF_SECONDS
        logger.debug("AI provider config store unavailable; using environment defaults")
        return None
    finally:
        if own_session and session is not None:
            try:
                session.close()
            except Exception:
                pass


def _decrypt(value: str | None) -> str:
    return decrypt_secret(value) if value else ""


def _resolve_text(
    row: Any | None,
    column: str,
    env_value: str,
) -> tuple[str, str]:
    raw = getattr(row, column, None) if row is not None else None
    if raw:
        decrypted = _decrypt(raw)
        if decrypted:
            return decrypted, "db"
    return env_value, "env" if env_value else "none"


def resolve_provider_config(
    provider: str,
    *,
    db: Session | None = None,
    use_cache: bool = True,
) -> ProviderRuntimeConfig:
    """Return the effective configuration for ``provider``."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unsupported AI provider: {provider}")

    defaults = _env_defaults(provider)
    fingerprint = _env_fingerprint(defaults)

    if use_cache:
        cached = _cache_get(provider, fingerprint)
        if cached is not None:
            return cached

    row = _db_row(provider, db)

    primary_model_raw = getattr(row, "primary_model", None) if row is not None else None
    alternate_model_raw = getattr(row, "alternate_model", None) if row is not None else None
    primary_model = (primary_model_raw or "").strip() or str(defaults["primary_model"])
    alternate_model = (alternate_model_raw or "").strip() or defaults["alternate_model"]
    primary_model_source = "db" if primary_model_raw else "env"
    if alternate_model is not None:
        alternate_model = str(alternate_model).strip() or None

    enabled = bool(defaults["enabled"])
    enabled_source = str(defaults["enabled_source"])
    if row is not None and getattr(row, "enabled", None) is not None:
        enabled = bool(row.enabled)
        enabled_source = "db"

    daily_limit = defaults["daily_limit"]
    if row is not None and getattr(row, "daily_limit", None) is not None:
        daily_limit = int(row.daily_limit)

    account_id, account_id_source = _resolve_text(row, "account_id_encrypted", str(defaults["account_id"]))
    alternate_account_id, alternate_account_id_source = _resolve_text(
        row, "alternate_account_id_encrypted", str(defaults["alternate_account_id"])
    )
    primary_key, primary_key_source = _resolve_text(
        row, "primary_api_key_encrypted", str(defaults["primary_api_key"])
    )
    alternate_key, alternate_key_source = _resolve_text(
        row, "alternate_api_key_encrypted", str(defaults["alternate_api_key"])
    )

    auto_failover = True
    if row is not None and getattr(row, "auto_failover_key", None) is not None:
        auto_failover = bool(row.auto_failover_key)

    active_slot = "primary"
    if row is not None and getattr(row, "active_key_slot", None) in KEY_SLOTS:
        active_slot = str(row.active_key_slot)

    updated_at = None
    if row is not None and getattr(row, "updated_at", None) is not None:
        try:
            updated_at = row.updated_at.isoformat()
        except Exception:
            updated_at = None

    config = ProviderRuntimeConfig(
        provider=provider,
        enabled=enabled,
        enabled_source=enabled_source,
        primary_model=primary_model,
        alternate_model=alternate_model,
        primary_model_source=primary_model_source,
        account_id=account_id,
        alternate_account_id=alternate_account_id,
        account_id_source=account_id_source,
        alternate_account_id_source=alternate_account_id_source,
        primary_api_key=primary_key,
        alternate_api_key=alternate_key,
        primary_key_source=primary_key_source,
        alternate_key_source=alternate_key_source,
        active_key_slot=active_slot,
        auto_failover_key=auto_failover,
        daily_limit=daily_limit,
        updated_at=updated_at,
    )
    if use_cache:
        _cache_put(provider, fingerprint, config)
    return config


def resolve_all_provider_configs(*, db: Session | None = None) -> dict[str, ProviderRuntimeConfig]:
    return {provider: resolve_provider_config(provider, db=db) for provider in PROVIDERS}


def provider_enabled(provider: str, *, db: Session | None = None) -> bool:
    try:
        return resolve_provider_config(provider, db=db).enabled
    except Exception:
        return False


def active_provider_key(provider: str, *, db: Session | None = None) -> str:
    try:
        return resolve_provider_config(provider, db=db).active_api_key
    except Exception:
        return ""


def auto_failover_enabled(provider: str, *, db: Session | None = None) -> bool:
    try:
        return resolve_provider_config(provider, db=db).auto_failover_key
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, tuple, ProviderRuntimeConfig]] = {}
_cache_lock = threading.Lock()


def _env_fingerprint(defaults: dict[str, Any]) -> tuple:
    """Hashable snapshot of the environment inputs that shape a config.

    Tests (and operators during a rolling restart) may change environment
    variables while the process is alive. Keying the cache on this snapshot
    keeps a five-second TTL from serving a stale environment-derived config.
    """
    return (
        os.environ.get("PMS_SECRETS_ENCRYPTION_KEY", ""),
        os.environ.get("JWT_SECRET", ""),
        tuple(sorted((str(key), repr(value)) for key, value in defaults.items())),
    )


def _cache_get(provider: str, fingerprint: tuple) -> ProviderRuntimeConfig | None:
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(provider)
        if entry is None:
            return None
        expires_at, cached_fingerprint, config = entry
        if now >= expires_at or cached_fingerprint != fingerprint:
            _cache.pop(provider, None)
            return None
        return config


def _cache_put(provider: str, fingerprint: tuple, config: ProviderRuntimeConfig) -> None:
    with _cache_lock:
        _cache[provider] = (time.monotonic() + CACHE_TTL_SECONDS, fingerprint, config)


def invalidate_provider_config(provider: str | None = None) -> None:
    """Drop cached configuration so the next call reads the database again."""
    with _cache_lock:
        if provider is None:
            _cache.clear()
        else:
            _cache.pop(provider, None)
