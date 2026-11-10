"""Redaction helpers for the Admin AI diagnostic.

The diagnostic payload itself is built next to the route. This module only
removes secrets from strings that might otherwise be copied into it.
"""

from __future__ import annotations

import os
import re
from typing import Any

from services.ai.config import redact_secrets

_SECRET_ENV_NAMES = (
    "PMS_AI_LLM_API_KEY",
    "PMS_AI_LLM_BASE_URL",
    "PMS_AI_LOCAL_ROUTER_URL",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "DATABASE_URL",
    "JWT_SECRET",
    "REDIS_PASSWORD",
)
_USERINFO_URL = re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:]+:[^/\s@]+@", re.IGNORECASE)
_BEARER = re.compile(r"Bearer\s+\S+", re.IGNORECASE)


def scrub_text(value: str) -> str:
    cleaned = redact_secrets(value)
    for name in _SECRET_ENV_NAMES:
        secret = os.environ.get(name, "")
        if secret and len(secret) >= 8 and secret in cleaned:
            cleaned = cleaned.replace(secret, "[REDACTED]")
    cleaned = _USERINFO_URL.sub("[REDACTED]", cleaned)
    return _BEARER.sub("[REDACTED]", cleaned)


def scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, list):
        return [scrub_value(item) for item in value]
    if isinstance(value, dict):
        return {key: scrub_value(item) for key, item in value.items()}
    return value
