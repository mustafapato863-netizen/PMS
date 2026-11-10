"""Optional intent suggestions from the configured self-hosted model.

PMS remains the source of facts. The model may only return one allowed intent.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from services.ai.runtime_status import note_fallback
from services.ai.llm_client import (
    chat_completion,
    configured_model_name,
    local_intent_enabled,
    routing_timeout_seconds,
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


def build_intent_json_schema() -> dict[str, object]:
    """Return strict JSON Schema for llama.cpp / OpenAI-compatible grammar enforcement."""
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

    def result(intent: str | None, reason: str, elapsed: float | None = None) -> LocalIntentResult:
        duration = elapsed if elapsed is not None else round((time.perf_counter() - started) * 1000, 2)
        return LocalIntentResult(intent, duration, reason, model)

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
        "Do not answer, calculate, or invent data. /no_think"
    )
    call = chat_completion(
        messages=[
            {"role": "system", "content": instruction},
            {"role": "user", "content": question.strip()},
        ],
        max_tokens=32,
        temperature=0,
        response_format={"type": "json_schema", "json_schema": build_intent_json_schema()},
        timeout_seconds=routing_timeout_seconds(),
        purpose="intent",
    )
    if not call.ok:
        reason = "unavailable_or_invalid" if call.reason == "http_error" else call.reason
        note_fallback(reason, "routing")
        return result(None, reason, call.elapsed_ms)
    try:
        cleaned = _JSON_FENCE_RE.sub("", call.content.strip() if call.content else "").strip()
        suggestion = json.loads(cleaned)
        if not isinstance(suggestion, dict) or set(suggestion) != {"intent"}:
            note_fallback("invalid_response", "routing")
            return result(None, "invalid_response", call.elapsed_ms)
        intent = suggestion["intent"]
        if not isinstance(intent, str) or intent not in ALLOWED_INTENTS:
            note_fallback("invalid_intent", "routing")
            return result(None, "invalid_intent", call.elapsed_ms)
        return result(intent, "ok", call.elapsed_ms)
    except (ValueError, TypeError, AttributeError):
        note_fallback("invalid_response", "routing")
        return result(None, "invalid_response", call.elapsed_ms)
