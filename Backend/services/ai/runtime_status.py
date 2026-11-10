"""In-memory, non-secret notes for the Admin AI diagnostic.

Reasons are short codes. Free text, prompts, and URLs are not stored.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

_LOCK = threading.Lock()
_FALLBACK_REASONS = frozenset(
    {
        "timeout",
        "http_error",
        "invalid_response",
        "invalid_json",
        "invalid_endpoint",
        "unavailable_or_invalid",
        "busy",
        "call_cap",
        "response_too_large",
        "invalid_or_unverified_response",
        "invalid_intent",
        "invalid_question",
        "disabled",
        "zero_or_missing_evidence",
        "model_unavailable",
        "cloud_disabled",
        "scope_not_allowed",
        "unsafe_prompt",
        "missing_api_key",
    }
)
_SOURCES = frozenset({"intent", "routing", "synthesis", "exploration", "llm", "probe"})
_last_fallback: dict[str, str | None] = {"reason": None, "source": None, "recorded_at": None}
_last_model: dict[str, str | None] = {"name": None, "observed_at": None}


def note_fallback(reason: str, source: str) -> None:
    """Remember the latest fallback code. Unknown text is stored as ``unspecified``."""
    code = str(reason or "").strip()
    if code not in _FALLBACK_REASONS:
        code = "unspecified"
    origin = str(source or "").strip()
    if origin not in _SOURCES:
        origin = "llm"
    recorded_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with _LOCK:
        _last_fallback["reason"] = code
        _last_fallback["source"] = origin
        _last_fallback["recorded_at"] = recorded_at


def last_fallback() -> dict[str, str | None]:
    with _LOCK:
        return dict(_last_fallback)


def remember_model(name: str) -> None:
    token = str(name or "").strip()
    if not token or len(token) > 80:
        return
    if any(char.isspace() for char in token):
        return
    recorded_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with _LOCK:
        _last_model["name"] = token
        _last_model["observed_at"] = recorded_at


def last_known_model() -> dict[str, str] | None:
    with _LOCK:
        name = _last_model["name"]
        observed_at = _last_model["observed_at"]
    if not name or not observed_at:
        return None
    return {"name": name, "observed_at": observed_at}


def reset_runtime_status() -> None:
    """Test helper. Production code does not clear this on a request."""
    with _LOCK:
        _last_fallback["reason"] = None
        _last_fallback["source"] = None
        _last_fallback["recorded_at"] = None
        _last_model["name"] = None
        _last_model["observed_at"] = None
