from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from config.environment import load_project_environment

# Load shared DevOps/.env and local overrides once when not running under pytest
_BACKEND_DIR = Path(__file__).resolve().parents[2]
if "pytest" not in sys.modules and "PYTEST_CURRENT_TEST" not in os.environ:
    load_project_environment(str(_BACKEND_DIR))
    _ENV_PATH = _BACKEND_DIR / ".env"
    if _ENV_PATH.exists():
        load_dotenv(dotenv_path=_ENV_PATH, override=False)

RouterModeType = Literal["legacy", "shadow", "hybrid"]
ClassifierModeType = Literal["off", "shadow", "enabled"]

SENIOR_BRIEF_DEFAULT_ROLES: frozenset[str] = frozenset(
    {
        "Executive",
        "General Manager",
        "Regional Manager",
        "Branch Director",
        "Function Director",
    }
)

DEFAULT_PILOT_SCOPES: frozenset[str] = frozenset(
    {
        "call center",
        "inbound",
        "outbound",
        "support positions",
        "rcm",
        "pre-approvals",
        "pre-approvals op final",
        "pre-approvals op dubai",
        "pre-approvals op final shjajm",
        "pre-approvals ip final",
        "pre-approvals ip final dubai",
        "pre-approvals ip final shjajm",
        "pre-approvals ip elective",
        "pre-approvals ip elective dubai",
        "pre-approvals ip offshore",
        "coding",
        "coding egy",
        "submission",
        "submission egy",
        "re-submission",
        "resubmission",
        "marketing",
        "pharmacy",
        "csr",
        "sales",
        "finance",
        "human resources",
        "it",
        "administration",
        "offshore admin & management",
    }
)

_API_KEY_PATTERN = re.compile(r"(?:AIza[0-9A-Za-z\-_]{20,}|AQ\.[0-9A-Za-z\-_]{20,}|oc_sk_[0-9A-Za-z\-_]{16,}|sk-[0-9A-Za-z\-_]{16,})")


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    norm = value.strip().casefold()
    if norm in ("1", "true", "yes", "on", "enabled"):
        return True
    if norm in ("0", "false", "no", "off", "disabled"):
        return False
    return default


@dataclass(frozen=True)
class AiRuntimeConfig:
    router_mode: RouterModeType
    gemini_routing_enabled: bool
    classifier_mode: ClassifierModeType
    brief_default_enabled: bool
    gemini_model: str
    gemini_api_key: str
    provider_timeout_seconds: float
    pilot_scopes: frozenset[str]
    redact_raw_prompts: bool

    @property
    def can_call_gemini(self) -> bool:
        return bool(self.gemini_routing_enabled and self.gemini_api_key)

    def is_scope_allowed_for_cloud(self, team_or_function: str | None) -> bool:
        if "*" in self.pilot_scopes:
            return True
        candidate = (team_or_function or "call center").strip().casefold()
        if candidate == "support positions":
            return candidate in self.pilot_scopes or "call center" in self.pilot_scopes
        return candidate in self.pilot_scopes

    def is_scope_enabled(self, team_or_function: str | None) -> bool:
        return self.is_scope_allowed_for_cloud(team_or_function)


def get_ai_runtime_config() -> AiRuntimeConfig:
    raw_router = os.environ.get("PMS_AI_ROUTER_MODE", "hybrid").strip().casefold()
    router_mode: RouterModeType = (
        raw_router if raw_router in ("legacy", "shadow", "hybrid") else "hybrid"  # type: ignore[assignment]
    )

    gemini_routing_enabled = _parse_bool(
        os.environ.get("PMS_AI_GEMINI_ROUTING_ENABLED"), default=False
    )

    raw_clf = os.environ.get("PMS_AI_CLASSIFIER_MODE", "off").strip().casefold()
    classifier_mode: ClassifierModeType = (
        raw_clf if raw_clf in ("off", "shadow", "enabled") else "off"  # type: ignore[assignment]
    )

    brief_default_enabled = _parse_bool(
        os.environ.get("PMS_AI_BRIEF_DEFAULT_ENABLED"), default=True
    )

    gemini_model = (
        os.environ.get("PMS_GEMINI_MODEL", "gemini-2.5-flash").strip()
        or "gemini-2.5-flash"
    )
    gemini_api_key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("Gemini_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    ).strip()

    try:
        timeout_val = float(os.environ.get("PMS_AI_PROVIDER_TIMEOUT_SECONDS", "4.0"))
        timeout_seconds = max(0.5, min(timeout_val, 10.0))
    except (TypeError, ValueError):
        timeout_seconds = 4.0

    raw_scopes = os.environ.get("PMS_AI_PILOT_SCOPES", "").strip()
    if raw_scopes:
        pilot_scopes = frozenset(
            s.strip().casefold() for s in raw_scopes.split(",") if s.strip()
        )
    else:
        pilot_scopes = DEFAULT_PILOT_SCOPES

    redact_raw_prompts = _parse_bool(
        os.environ.get("PMS_AI_TRACE_REDACT_RAW_PROMPT"), default=True
    )

    return AiRuntimeConfig(
        router_mode=router_mode,
        gemini_routing_enabled=gemini_routing_enabled,
        classifier_mode=classifier_mode,
        brief_default_enabled=brief_default_enabled,
        gemini_model=gemini_model,
        gemini_api_key=gemini_api_key,
        provider_timeout_seconds=timeout_seconds,
        pilot_scopes=pilot_scopes,
        redact_raw_prompts=redact_raw_prompts,
    )


def redact_secrets(text: str) -> str:
    """Ensure API keys or bearer tokens never leak into logs, traces, or error messages."""
    if not text:
        return ""
    cleaned = _API_KEY_PATTERN.sub("[REDACTED_API_KEY]", str(text))
    cleaned = re.sub(r"([?&]key=)[^&\s]+", r"\1[REDACTED_API_KEY]", cleaned, flags=re.IGNORECASE)
    return cleaned
