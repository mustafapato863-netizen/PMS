"""Optional intent suggestions from the configured AI provider (Cloudflare primary, Gemini fallback).

PMS remains the source of facts. The model may only return one allowed intent.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from services.ai.llm_client import (
    active_provider_name,
    configured_model_name,
    local_intent_enabled,
    record_fallback_reason,
    routing_timeout_seconds,
)
from services.ai.provider_engine import (
    ProviderMessage,
    ProviderRequest,
    get_unified_provider_engine,
)

__all__ = ["ALLOWED_INTENTS", "LocalIntentResult", "build_intent_json_schema", "local_intent_enabled", "suggest_intent"]

ALLOWED_INTENTS = frozenset(
    {
        "current_value",
        "actual_vs_target",
        "trend",
        "ranking",
        "score_drivers",
        "page_help",
        "navigation",
        "proposal",
        "clarify",
    }
)

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass(frozen=True)
class LocalIntentResult:
    intent: str | None
    elapsed_ms: float
    reason: str
    model: str = ""
    provider: str = "cloudflare"


def _fallback_provider_name() -> str:
    name = active_provider_name()
    return name if name in ("cloudflare", "gemini") else "cloudflare"


def _resolve_provider(name: str | None) -> str:
    """``provider`` is always exactly ``cloudflare`` or ``gemini``."""
    return name if name in ("cloudflare", "gemini") else _fallback_provider_name()


def build_intent_json_schema() -> dict[str, object]:
    """Return strict JSON Schema for provider-side structured output."""
    return {
        "name": "intent_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": sorted(ALLOWED_INTENTS),
                }
            },
            "required": ["intent"],
            "additionalProperties": False,
        },
    }


def suggest_intent(question: str) -> LocalIntentResult:
    """Ask the configured model for an intent only, never scores, identities or SQL.

    The result is an untrusted suggestion. The caller must verify completeness,
    enforce authorization and compute every answer through PMS services.
    """
    started = time.perf_counter()
    model = configured_model_name()

    def result(intent: str | None, reason: str, elapsed: float | None = None, prov: str | None = None) -> LocalIntentResult:
        duration = elapsed if elapsed is not None else round((time.perf_counter() - started) * 1000, 2)
        return LocalIntentResult(intent, duration, reason, model, provider=prov or _fallback_provider_name())

    if not local_intent_enabled():
        return result(None, "disabled")
    if not question or not question.strip() or len(question) > 600:
        return result(None, "invalid_question")
    instruction = (
        "Classify the user's PMS question into one intent. Return JSON with only an intent field. "
        "Allowed intents: "
        "page_help (what does this page show, explain this view or metric definition), "
        "navigation (where can I find a page, scorecard, or feature), "
        "proposal (suggest or create a corrective action or improvement plan), "
        "current_value (single metric or score value), "
        "actual_vs_target (metric compared against target), "
        "trend (how a metric or score changed over time/months), "
        "ranking (best, top, worst, or lowest performer), "
        "score_drivers (why a score or metric is low/high, root causes, KPI gaps), "
        "clarify (ambiguous or missing scope). "
        "Do not answer, calculate, or invent data."
    )
    req = ProviderRequest(
        messages=[
            ProviderMessage(role="user", content=question.strip()),
        ],
        system_instruction=instruction,
        response_format="json",
        json_schema=build_intent_json_schema()["schema"],
        temperature=0.0,
        max_tokens=32,
        timeout_seconds=routing_timeout_seconds(),
        purpose="intent",
    )
    engine = get_unified_provider_engine()
    resp = engine.generate(req)
    prov_used = _resolve_provider(resp.provider)
    if not resp.is_success:
        reason = resp.outcome or "unavailable_or_invalid"
        record_fallback_reason(reason)
        return result(None, reason, resp.latency_ms, prov=prov_used)

    try:
        cleaned = _JSON_FENCE_RE.sub("", resp.content.strip() if resp.content else "").strip()
        suggestion = json.loads(cleaned)
        if not isinstance(suggestion, dict) or set(suggestion) != {"intent"}:
            return result(None, "invalid_response", resp.latency_ms, prov=prov_used)
        intent = suggestion["intent"]
        if not isinstance(intent, str) or intent not in ALLOWED_INTENTS:
            return result(None, "invalid_intent", resp.latency_ms, prov=prov_used)
        return LocalIntentResult(intent, resp.latency_ms, "ok", resp.model or model, provider=prov_used)
    except (ValueError, TypeError, AttributeError):
        return result(None, "invalid_response", resp.latency_ms, prov=prov_used)
