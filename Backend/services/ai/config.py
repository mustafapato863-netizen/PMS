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
else:
    # Ensure unit tests start with cloud/local model routing disabled by default unless monkeypatched by a test
    os.environ["PMS_AI_NVIDIA_ROUTING_ENABLED"] = "false"
    os.environ["PMS_AI_LOCAL_ROUTER_ENABLED"] = "false"
    os.environ["PMS_AI_LOCAL_EXPLORATION_ENABLED"] = "false"

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
        "pre-approvals ip",
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
        "crm",
        "nursing",
        "pmo",
    }
)

_API_KEY_PATTERN = re.compile(
    r"(?:nvapi-[0-9A-Za-z\-_]{16,}|cfut_[0-9A-Za-z\-_]{20,}|Bearer\s+[0-9A-Za-z\-_]{20,}|AIza[0-9A-Za-z\-_]{20,}|AQ\.[0-9A-Za-z\-_]{20,}|oc_sk_[0-9A-Za-z\-_]{16,}|sk-[0-9A-Za-z\-_]{16,})",
    flags=re.IGNORECASE,
)


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
    nvidia_routing_enabled: bool
    classifier_mode: ClassifierModeType
    brief_default_enabled: bool
    provider_timeout_seconds: float
    pilot_scopes: frozenset[str]
    redact_raw_prompts: bool
    conversation_state_enabled: bool = True
    model_led_pilot_enabled: bool = False
    guided_reads_enabled: bool = False

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

    nvidia_routing_enabled = _parse_bool(
        os.environ.get("PMS_AI_NVIDIA_ROUTING_ENABLED"), default=False
    )

    app_env = os.environ.get("APP_ENV", "").strip().casefold()
    classifier_mode: ClassifierModeType = "off"

    brief_default_enabled = _parse_bool(
        os.environ.get("PMS_AI_BRIEF_DEFAULT_ENABLED"), default=True
    )

    try:
        timeout_val = float(os.environ.get("PMS_AI_PROVIDER_TIMEOUT_SECONDS", "18.0"))
        timeout_seconds = max(0.5, min(timeout_val, 45.0))
    except (TypeError, ValueError):
        timeout_seconds = 18.0

    raw_scopes = (
        os.environ.get("PMS_AI_ENABLED_SCOPES")
        or os.environ.get("PMS_AI_PILOT_SCOPES")
        or ""
    ).strip()
    if raw_scopes:
        pilot_scopes = frozenset(
            s.strip().casefold() for s in raw_scopes.split(",") if s.strip()
        )
    else:
        pilot_scopes = DEFAULT_PILOT_SCOPES

    redact_raw_prompts = _parse_bool(
        os.environ.get("PMS_AI_TRACE_REDACT_RAW_PROMPT"), default=True
    )
    conversation_state_enabled = _parse_bool(
        os.environ.get("PMS_AI_CONVERSATION_STATE_ENABLED"), default=True
    )
    model_led_pilot_enabled = _parse_bool(
        os.environ.get("PMS_AI_MODEL_LED_PILOT_ENABLED"), default=False
    )
    guided_reads_enabled = _parse_bool(
        os.environ.get("PMS_AI_GUIDED_READS_ENABLED"), default=False
    )

    return AiRuntimeConfig(
        router_mode=router_mode,
        nvidia_routing_enabled=nvidia_routing_enabled,
        classifier_mode=classifier_mode,
        brief_default_enabled=brief_default_enabled,
        provider_timeout_seconds=timeout_seconds,
        pilot_scopes=pilot_scopes,
        redact_raw_prompts=redact_raw_prompts,
        conversation_state_enabled=conversation_state_enabled,
        model_led_pilot_enabled=model_led_pilot_enabled,
        guided_reads_enabled=guided_reads_enabled,
    )


def redact_secrets(text: str) -> str:
    """Ensure API keys, bearer tokens, or account IDs never leak into logs, traces, or error messages."""
    if not text:
        return ""
    cleaned = _API_KEY_PATTERN.sub("[REDACTED_API_KEY]", str(text))
    cleaned = re.sub(r"([?&]key=)[^&\s]+", r"\1[REDACTED_API_KEY]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(accounts/)[0-9a-f]{32}(/ai)", r"\1[REDACTED_ACCOUNT_ID]\2", cleaned, flags=re.IGNORECASE)
    return cleaned
