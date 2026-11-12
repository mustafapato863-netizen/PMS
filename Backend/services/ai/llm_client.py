"""Provider-agnostic AI settings for the PMS assistant.

All model traffic goes through ``services.ai.provider_engine``: Cloudflare
Workers AI is primary and Google Gemini is the fallback. This module no longer
contains any transport, self-hosted model, inference-slot or health-probe code.
It only answers "is this AI feature on?", "what are the time and size limits?"
and "which provider/model is configured?". PMS still computes every number; a
provider failure is a reason code and the caller falls back to the rules engine.

Feature gates
-------------
Intent routing and validated synthesis are on when a provider is usable
(Cloudflare or Gemini enabled *and* credentialed). ``PMS_AI_INTENT_ENABLED`` /
``PMS_AI_SYNTHESIS_ENABLED`` may force them off (or on). Tool-planning
exploration stays opt-in via ``PMS_AI_EXPLORATION_ENABLED`` and is always off
when ``APP_ENV=production``. The global kill switch remains the database-backed
``read_ai_enabled`` feature gate.
"""

from __future__ import annotations

import os
import re
import threading
import time
from typing import Any

from services.ai.provider_engine import UnifiedProviderConfig, load_unified_provider_config

SUPPORTED_PROVIDERS = ("cloudflare", "gemini")

_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_THINK_OPEN_RE = re.compile(r"<think\b[^>]*>.*", re.IGNORECASE | re.DOTALL)
_TRUTHY = {"1", "true", "yes", "on", "enabled"}
_FALSY = {"0", "false", "no", "off", "disabled"}

_fallback_lock = threading.Lock()
_last_fallback_reason: str = "none"


def get_recent_fallback_reason() -> str:
    with _fallback_lock:
        return _last_fallback_reason


def record_fallback_reason(reason: str | None) -> None:
    """Remember why the most recent provider call fell back (process-local)."""
    global _last_fallback_reason
    if reason:
        with _fallback_lock:
            _last_fallback_reason = str(reason)[:80]


def flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().casefold() in _TRUTHY


def _tri_state(*names: str) -> bool | None:
    """First explicitly set name wins; ``None`` when none is set to a recognised value."""
    for name in names:
        raw = os.environ.get(name, "").strip().casefold()
        if raw in _TRUTHY:
            return True
        if raw in _FALSY:
            return False
    return None


# ---------------------------------------------------------------------------
# Provider availability (configuration only; no network probe)
# ---------------------------------------------------------------------------


def _provider_ready(config: UnifiedProviderConfig, provider: str) -> bool:
    if provider == "cloudflare":
        return bool(config.cloudflare_enabled and config.cloudflare_account_id and config.cloudflare_api_token)
    if provider == "gemini":
        return bool(config.gemini_enabled and config.gemini_api_key)
    return False  # any other provider name (including "openai") is never usable


def configured_providers(config: UnifiedProviderConfig | None = None) -> list[str]:
    """Usable providers in call order: primary first, then fallback when allowed."""
    cfg = config or load_unified_provider_config()
    order = [cfg.effective_primary_provider]
    if cfg.fallback_enabled:
        order.append(cfg.effective_fallback_provider)
    seen: list[str] = []
    for name in order:
        if name in SUPPORTED_PROVIDERS and name not in seen and _provider_ready(cfg, name):
            seen.append(name)
    return seen


def provider_available() -> bool:
    return bool(configured_providers())


def active_provider_name() -> str:
    """Provider that would serve the next call, or ``deterministic`` when none is usable."""
    providers = configured_providers()
    return providers[0] if providers else "deterministic"


def local_intent_enabled() -> bool:
    """Intent routing is safe in production: the model returns one enum, PMS does the rest."""
    explicit = _tri_state("PMS_AI_INTENT_ENABLED", "PMS_AI_LOCAL_ROUTER_ENABLED")
    return explicit if explicit is not None else provider_available()


def local_synthesis_enabled() -> bool:
    """Validated synthesis is safe in production. Rejected text falls back to the rules headline."""
    explicit = _tri_state("PMS_AI_SYNTHESIS_ENABLED", "PMS_AI_LOCAL_SYNTHESIS_ENABLED")
    return explicit if explicit is not None else provider_available()


def local_exploration_enabled() -> bool:
    """Tool-planning stays off in production.

    The host allowlist does not limit which authorized question the model asks
    PMS to run, and each step can send evidence summaries to the provider.
    Intent routing and validated synthesis do neither.
    """
    if os.environ.get("APP_ENV", "").strip().casefold() == "production":
        return False
    data_flag = os.environ.get("PMS_AI_LOCAL_DATA_EXPLORATION_ENABLED", "").strip().casefold()
    if data_flag in _FALSY:
        return False
    return flag_enabled("PMS_AI_EXPLORATION_ENABLED") or flag_enabled("PMS_AI_LOCAL_EXPLORATION_ENABLED") or data_flag in _TRUTHY


def configured_model_name() -> str:
    """Primary model name for display and tracing (Cloudflare unless Gemini leads)."""
    cfg = load_unified_provider_config()
    primary = cfg.effective_primary_provider
    if primary == "gemini":
        return cfg.gemini_model
    return cfg.cloudflare_model


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------


def _bounded_float(names: tuple[str, ...], default: float, maximum: float) -> float:
    raw = ""
    for name in names:
        candidate = os.environ.get(name, "").strip()
        if candidate:
            raw = candidate
            break
    try:
        value = float(raw) if raw else default
    except ValueError:
        value = default
    return max(0.5, min(value, maximum))


def routing_timeout_seconds() -> float:
    """Intent routing deadline. Default 10s, hard cap 30s."""
    return _bounded_float(("PMS_AI_ROUTER_TIMEOUT_SECONDS", "PMS_AI_PROVIDER_TIMEOUT_SECONDS", "PMS_AI_TIMEOUT_SECONDS"), 10.0, 30.0)


def synthesis_timeout_seconds() -> float:
    """Synthesis / drafting deadline. Default 15s, hard cap 60s."""
    return _bounded_float(("PMS_AI_SYNTHESIS_TIMEOUT_SECONDS", "PMS_AI_PROVIDER_TIMEOUT_SECONDS", "PMS_AI_TIMEOUT_SECONDS"), 15.0, 60.0)


def exploration_timeout_seconds() -> float:
    return _bounded_float(("PMS_AI_EXPLORATION_TIMEOUT_SECONDS", "PMS_AI_PROVIDER_TIMEOUT_SECONDS", "PMS_AI_TIMEOUT_SECONDS"), 15.0, 30.0)


def context_token_limit() -> int:
    """Prompt budget used to refuse oversized evidence instead of truncating it."""
    raw = os.environ.get("PMS_AI_CONTEXT_TOKENS", "8192").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 8192
    return max(512, min(value, 32768))


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def strip_thinking(text: str) -> str:
    """Drop reasoning ``<think>`` blocks some models emit so JSON parsers see only the answer."""
    cleaned = _THINK_BLOCK_RE.sub("", text or "")
    cleaned = _THINK_OPEN_RE.sub("", cleaned)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Diagnostics (configuration & verification state; never makes a network call, never returns secrets)
# ---------------------------------------------------------------------------

DIAGNOSTIC_STATUS_CONFIGURED = "configured"
DIAGNOSTIC_STATUS_CREDENTIALS_PRESENT = "credentials_present"
DIAGNOSTIC_STATUS_LIVE_VERIFIED = "live_verified"
DIAGNOSTIC_STATUS_LIVE_FAILED = "live_failed"
DIAGNOSTIC_STATUS_FALLBACK_ACTIVE = "fallback_active"
DIAGNOSTIC_STATUS_UNAVAILABLE = "unavailable"

DIAGNOSTIC_STATUSES = (
    DIAGNOSTIC_STATUS_CONFIGURED,
    DIAGNOSTIC_STATUS_CREDENTIALS_PRESENT,
    DIAGNOSTIC_STATUS_LIVE_VERIFIED,
    DIAGNOSTIC_STATUS_LIVE_FAILED,
    DIAGNOSTIC_STATUS_FALLBACK_ACTIVE,
    DIAGNOSTIC_STATUS_UNAVAILABLE,
)

# Short aliases for tests and external callers
STATUS_CONFIGURED = DIAGNOSTIC_STATUS_CONFIGURED
STATUS_CREDENTIALS_PRESENT = DIAGNOSTIC_STATUS_CREDENTIALS_PRESENT
STATUS_LIVE_VERIFIED = DIAGNOSTIC_STATUS_LIVE_VERIFIED
STATUS_LIVE_FAILED = DIAGNOSTIC_STATUS_LIVE_FAILED
STATUS_FALLBACK_ACTIVE = DIAGNOSTIC_STATUS_FALLBACK_ACTIVE
STATUS_UNAVAILABLE = DIAGNOSTIC_STATUS_UNAVAILABLE

_live_verification_lock = threading.Lock()
_last_live_verification: dict[str, Any] | None = None


def record_live_verification(result: dict[str, Any]) -> None:
    """Record the result of an explicit Admin-only live verification check (process-local)."""
    global _last_live_verification
    with _live_verification_lock:
        is_verified = bool(result.get("verified"))
        _last_live_verification = {
            "verified": is_verified,
            "status": DIAGNOSTIC_STATUS_LIVE_VERIFIED if is_verified else DIAGNOSTIC_STATUS_LIVE_FAILED,
            "provider": str(result.get("provider") or "cloudflare"),
            "model": str(result.get("model") or ""),
            "latency_ms": float(result.get("total_latency_ms") or 0.0),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "error": str(result.get("error")) if result.get("error") else None,
        }


def get_live_verification() -> dict[str, Any] | None:
    """Retrieve the cached result of the most recent live verification check (process-local)."""
    with _live_verification_lock:
        return dict(_last_live_verification) if _last_live_verification else None


def clear_live_verification() -> None:
    """Clear cached live verification result (useful for test resets)."""
    global _last_live_verification
    with _live_verification_lock:
        _last_live_verification = None


_PROVIDER_HOSTS = {
    "cloudflare": "api.cloudflare.com",
    "gemini": "generativelanguage.googleapis.com",
}


def provider_status(config: UnifiedProviderConfig | None = None) -> dict[str, object]:
    """Credential-free snapshot of the provider hierarchy for admin diagnostics.
    
    Distinguishes 6 diagnostic states:
    - configured: Enabled in config but missing required credentials
    - credentials_present: Valid credentials configured, live inference not run
    - live_verified: Explicit live inference succeeded and validated
    - live_failed: Explicit live inference was attempted and failed
    - fallback_active: Fallback provider is currently serving requests
    - unavailable: Provider disabled, unconfigured, or unusable
    
    Never makes an external network call; routine diagnostic reads never consume AI tokens.
    """
    import time
    cfg = config or load_unified_provider_config()
    primary = cfg.effective_primary_provider
    usable = configured_providers(cfg)
    lead = usable[0] if usable else primary

    live_info = get_live_verification()
    fallback_reason = get_recent_fallback_reason()

    if not usable:
        if (primary == "cloudflare" and not cfg.cloudflare_enabled) or (not cfg.cloudflare_enabled and not cfg.gemini_enabled):
            status_code = DIAGNOSTIC_STATUS_UNAVAILABLE
            reason = "disabled"
        else:
            status_code = DIAGNOSTIC_STATUS_CONFIGURED
            reason = "no_credentials_configured"
    else:
        # Credentials are present for at least one provider
        if live_info is not None:
            if live_info.get("verified"):
                status_code = DIAGNOSTIC_STATUS_LIVE_VERIFIED
                reason = "live_verified"
            else:
                status_code = DIAGNOSTIC_STATUS_LIVE_FAILED
                reason = "live_failed"
        elif lead == cfg.effective_fallback_provider and lead != primary:
            status_code = DIAGNOSTIC_STATUS_FALLBACK_ACTIVE
            reason = "fallback_active" if fallback_reason not in ("none", "") else "primary_unconfigured_fallback_only"
        elif fallback_reason not in ("none", "") and lead == cfg.effective_fallback_provider:
            status_code = DIAGNOSTIC_STATUS_FALLBACK_ACTIVE
            reason = "fallback_active"
        else:
            status_code = DIAGNOSTIC_STATUS_CREDENTIALS_PRESENT
            reason = "configured" if lead == primary else "primary_unconfigured_fallback_only"

    return {
        "primary_provider": primary,
        "fallback_provider": cfg.effective_fallback_provider if cfg.fallback_enabled else None,
        "configured_model": cfg.gemini_model if lead == "gemini" else cfg.cloudflare_model,
        "endpoint_configured": bool(usable),
        "endpoint_host": _PROVIDER_HOSTS.get(lead) if usable else None,
        "available": bool(usable),
        "active_provider": lead if usable else "deterministic",
        "reason": reason,
        "status_code": status_code,
        "live_verified": bool(live_info and live_info.get("verified")),
        "live_verification": live_info,
    }
