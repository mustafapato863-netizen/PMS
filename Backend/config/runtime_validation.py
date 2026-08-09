"""Pure runtime configuration validation shared by settings and database setup."""

from __future__ import annotations

import logging
from collections.abc import Mapping


DEVELOPMENT_JWT_FALLBACK = "pms-development-only-jwt-secret-key-2026"


class RuntimeConfigurationError(RuntimeError):
    """Raised when a deployment environment is unsafe or incomplete."""


def is_production(app_env: str | None) -> bool:
    return (app_env or "development").strip().lower() == "production"


def resolve_jwt_secret(secret: str | None, app_env: str | None) -> str:
    value = (secret or "").strip()
    if not is_production(app_env):
        return value or DEVELOPMENT_JWT_FALLBACK

    if not value:
        raise RuntimeConfigurationError("JWT_SECRET is required when APP_ENV=production.")

    lowered = value.lower()
    placeholder_markers = (
        "<replace",
        "change-me",
        "changeme",
        "generate-a-secure",
        "default-jwt",
        "development-only",
    )
    if len(value) < 32 or any(marker in lowered for marker in placeholder_markers):
        raise RuntimeConfigurationError(
            "JWT_SECRET must be a non-placeholder secret of at least 32 characters in production."
        )
    return value


def validate_seed_settings(app_env: str | None, flags: Mapping[str, bool]) -> None:
    if not is_production(app_env):
        return

    enabled = sorted(name for name, value in flags.items() if value)
    if enabled:
        raise RuntimeConfigurationError(
            "Automatic startup seeding is forbidden in production: " + ", ".join(enabled)
        )


def resolve_database_url(
    database_url: str | None,
    app_env: str | None,
    *,
    logger: logging.Logger | None = None,
) -> str:
    value = (database_url or "").strip()
    if is_production(app_env):
        if not value:
            raise RuntimeConfigurationError(
                "DATABASE_URL is required when APP_ENV=production; SQLite fallback is disabled."
            )
        if not value.lower().startswith(("postgresql://", "postgresql+")):
            raise RuntimeConfigurationError(
                "DATABASE_URL must use PostgreSQL when APP_ENV=production."
            )
        return value

    if value:
        return value

    (logger or logging.getLogger(__name__)).warning(
        "DATABASE_URL is not set. Using the development/test SQLite fallback."
    )
    return "sqlite:///./pms_fallback.db"
