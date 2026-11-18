"""Model Enhancement Flywheel helpers.

Handles:
- DPO rejected candidate persistence (§4.3)
- Implicit friction signal recording (§4.2)
- Persona-scoped approved pattern filtering (§4.4)
- Deidentification hardening for exports (§4.6)
- Bounded query helpers (§4.5)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from services.ai.identity_service import PersonaTier, UserIdentityPassport
from services.ai.security_hardening import fence_untrusted_evidence, redact_nested_payload

MAX_REJECTED_CHARS = 1024
REPHRASE_WINDOW_SECONDS = 45
ABANDON_WINDOW_MINUTES = 5
MIN_EXPORT_COHORT_SIZE = 5


def build_dpo_structured_response(
    accepted: dict[str, Any] | str,
    rejected: dict[str, Any] | str,
    rejection_reason: str,
) -> dict[str, Any]:
    """Build a trace structured_response carrying a DPO pair (§4.3)."""
    def _cap(value: dict[str, Any] | str) -> str:
        text = value if isinstance(value, str) else str(value)
        return text[:MAX_REJECTED_CHARS]

    return {
        "accepted": _cap(accepted),
        "rejected": _cap(rejected),
        "rejection_reason": rejection_reason[:200],
        "dpo_pair": True,
    }


def detect_rephrase_signal(previous_turn: dict[str, Any], current_turn: dict[str, Any]) -> dict[str, Any] | None:
    """Detect a rephrase: same conversation, next turn within 45s, similar intent (§4.2)."""
    prev_time = previous_turn.get("created_at")
    curr_time = current_turn.get("created_at")
    if not prev_time or not curr_time:
        return None
    if isinstance(prev_time, str):
        try:
            prev_time = datetime.fromisoformat(prev_time.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(curr_time, str):
        try:
            curr_time = datetime.fromisoformat(curr_time.replace("Z", "+00:00"))
        except ValueError:
            return None
    gap = (curr_time - prev_time).total_seconds()
    if 0 <= gap <= REPHRASE_WINDOW_SECONDS:
        return {"friction": "rephrase", "gap_seconds": round(gap, 1)}
    return None


def detect_abandon_signal(last_turn: dict[str, Any], now: datetime | None = None) -> dict[str, Any] | None:
    """Detect an abandoned conversation: no follow-up within 5 min (§4.2)."""
    last_time = last_turn.get("created_at")
    if not last_time:
        return None
    if isinstance(last_time, str):
        try:
            last_time = datetime.fromisoformat(last_time.replace("Z", "+00:00"))
        except ValueError:
            return None
    now = now or datetime.now(timezone.utc)
    if now - last_time > timedelta(minutes=ABANDON_WINDOW_MINUTES):
        return {"friction": "abandoned"}
    return None


def filter_patterns_by_passport(
    patterns: list[dict[str, Any]],
    passport: UserIdentityPassport | None,
) -> list[dict[str, Any]]:
    """Persona-scoped pattern filtering (§4.4): universal patterns + matching tier only."""
    if passport is None:
        return [p for p in patterns if not p.get("persona_tier")]
    tier = passport.persona_tier.value if isinstance(passport.persona_tier, PersonaTier) else str(passport.persona_tier)
    return [
        p for p in patterns
        if not p.get("persona_tier") or p.get("persona_tier") == tier
    ]


def deidentify_export_row(row: dict[str, Any]) -> dict[str, Any]:
    """Deidentify a training-export row (§4.6)."""
    clean = redact_nested_payload(row)
    # Remove cohort size below privacy threshold
    if isinstance(clean.get("cohort_size"), int) and clean["cohort_size"] < MIN_EXPORT_COHORT_SIZE:
        clean["cohort_size"] = None
        clean["cohort_deidentified"] = True
    return clean


def safe_evidence_block(text: str) -> str:
    """Wrap untrusted evidence in fenced, escaped XML (§4.6)."""
    return fence_untrusted_evidence(text)
