"""Optional intent suggestions from the configured AI provider (NVIDIA primary, Cloudflare fallback).

PMS remains the source of facts. The model may only return one allowed intent.
"""

from __future__ import annotations

import inspect
import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable

from services.ai.llm_client import (
    active_provider_name,
    configured_model_name,
    local_intent_enabled,
    record_fallback_reason,
    routing_timeout_seconds,
)
from services.ai.prompt_versions import INTENT_CLASSIFIER_PROMPT_VERSION
from services.ai.provider_engine import (
    ProviderMessage,
    ProviderRequest,
    get_unified_provider_engine,
)

__all__ = [
    "ALLOWED_INTENTS",
    "BoundedIntentContext",
    "LocalIntentResult",
    "build_intent_json_schema",
    "call_suggest_intent",
    "local_intent_enabled",
    "suggest_intent",
]

ALLOWED_INTENTS = frozenset(
    {
        "greeting",
        "capabilities_help",
        "explain_previous",
        "off_topic",
        "clarification",
        "performance_query",
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


@dataclass(frozen=True)
class BoundedIntentContext:
    """Server-owned bounded conversation context passed to the intent classifier."""

    confirmed_function: str | None = None
    confirmed_team: str | None = None
    confirmed_region: str | None = None
    confirmed_branch: str | None = None
    confirmed_level: str | None = None
    confirmed_metric: str | None = None
    confirmed_periods: tuple[str, ...] = field(default_factory=tuple)
    previous_operation: str | None = None
    has_confirmed_employee: bool = False
    pending_clarification_code: str | None = None
    last_answer_summary: str | None = None

    def to_compact_dict(self) -> dict[str, object]:
        out: dict[str, object] = {}
        if self.confirmed_function:
            out["function"] = self.confirmed_function
        if self.confirmed_team:
            out["team"] = self.confirmed_team
        if self.confirmed_region:
            out["country"] = self.confirmed_region
        if self.confirmed_branch:
            out["branch"] = self.confirmed_branch
        if self.confirmed_level:
            out["level"] = self.confirmed_level
        if self.confirmed_metric:
            out["metric"] = self.confirmed_metric
        if self.confirmed_periods:
            out["periods"] = list(self.confirmed_periods[:3])
        if self.previous_operation:
            out["previous_operation"] = self.previous_operation
        if self.has_confirmed_employee:
            out["has_confirmed_employee"] = True
        if self.pending_clarification_code:
            out["pending_clarification"] = self.pending_clarification_code
        if self.last_answer_summary:
            out["previous_answer_summary"] = self.last_answer_summary[:220]
        return out

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass(frozen=True)
class LocalIntentResult:
    intent: str | None
    elapsed_ms: float
    reason: str
    model: str = ""
    provider: str = "cloudflare"
    input_tokens: int = 0
    output_tokens: int = 0
    neurons: int = 0
    estimated_cost_usd: float = 0.0
    cost_status: str = "not_applicable"


def _fallback_provider_name() -> str:
    name = active_provider_name()
    return name if name in ("cloudflare", "nvidia") else "cloudflare"


def _resolve_provider(name: str | None) -> str:
    """``provider`` is always exactly ``cloudflare`` or ``nvidia``."""
    return name if name in ("cloudflare", "nvidia") else _fallback_provider_name()


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


def call_suggest_intent(
    fn: Callable[..., LocalIntentResult],
    question: str,
    context: BoundedIntentContext | None = None,
    *,
    user_id: str | None = None,
    user_role: str | None = None,
) -> LocalIntentResult:
    """Invoke suggest_intent (or a 1-arg test double) cleanly with optional bounded context."""
    try:
        sig = inspect.signature(fn)
        kwargs: dict[str, object] = {}
        accepts_var_kw = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
        if accepts_var_kw or "context" in sig.parameters:
            kwargs["context"] = context
        if accepts_var_kw or "user_id" in sig.parameters:
            kwargs["user_id"] = user_id
        if accepts_var_kw or "user_role" in sig.parameters:
            kwargs["user_role"] = user_role
        if kwargs:
            return fn(question, **kwargs)
    except (ValueError, TypeError):
        pass
    return fn(question)


def suggest_intent(
    question: str,
    context: BoundedIntentContext | None = None,
    *,
    user_id: str | None = None,
    user_role: str | None = None,
) -> LocalIntentResult:
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
        f"[PromptVersion: {INTENT_CLASSIFIER_PROMPT_VERSION}]\n"
        "Classify the user's message into one intent. Return JSON with only an intent field. "
        "Allowed intents: "
        "greeting (salutations or thanks like hi, hello, thanks), "
        "capabilities_help (asking what the assistant can do or how it can help, even when naming a team or department), "
        "explain_previous (asking what the previous assistant answer meant, e.g. 'what do you mean', 'explain that', 'clarify'), "
        "off_topic (non-PMS topics like weather, recipes, jokes, movies, sports, general trivia), "
        "clarification (vague data-less request missing team, KPI, person, or overview scope, or a bare period/country without active context), "
        "performance_query (broad PMS performance overview request, follow-up refinement, or explicit correction of an active query), "
        "page_help (what does this page show, explain this view or metric definition), "
        "navigation (where can I find a page, scorecard, or feature), "
        "proposal (suggest or create a corrective action or improvement plan), "
        "current_value (single metric or score value), "
        "actual_vs_target (metric compared against target), "
        "trend (how a metric or score changed over time/months), "
        "ranking (best, top, worst, or lowest performer), "
        "score_drivers (why a score or metric is low/high, root causes, KPI gaps), "
        "clarify (ambiguous or missing scope). "
        "Do not answer, calculate, invent filters, or invent data."
    )
    compact_ctx = context.to_compact_dict() if context is not None else {}
    if compact_ctx:
        instruction = f"{instruction}\nBounded conversation context: {json.dumps(compact_ctx, ensure_ascii=False)}"
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
        task_role="routine",
        user_id=user_id,
        user_role=user_role,
    )
    engine = get_unified_provider_engine()
    resp = engine.generate(req)
    prov_used = _resolve_provider(resp.provider)
    from services.ai.providers import metrics_from_provider_response

    pm = metrics_from_provider_response(resp)
    if not resp.is_success:
        reason = resp.outcome or "unavailable_or_invalid"
        record_fallback_reason(reason)
        return LocalIntentResult(
            None,
            resp.latency_ms,
            reason,
            model,
            provider=prov_used,
            input_tokens=pm.input_tokens,
            output_tokens=pm.output_tokens,
            neurons=pm.neurons,
            estimated_cost_usd=pm.estimated_cost_usd,
            cost_status=pm.cost_status,
        )

    try:
        cleaned = _JSON_FENCE_RE.sub("", resp.content.strip() if resp.content else "").strip()
        suggestion = json.loads(cleaned)
        if not isinstance(suggestion, dict) or set(suggestion) != {"intent"}:
            return LocalIntentResult(
                None,
                resp.latency_ms,
                "invalid_response",
                model,
                provider=prov_used,
                input_tokens=pm.input_tokens,
                output_tokens=pm.output_tokens,
                neurons=pm.neurons,
                estimated_cost_usd=pm.estimated_cost_usd,
                cost_status=pm.cost_status,
            )
        intent = suggestion["intent"]
        if not isinstance(intent, str) or intent not in ALLOWED_INTENTS:
            return LocalIntentResult(
                None,
                resp.latency_ms,
                "invalid_intent",
                model,
                provider=prov_used,
                input_tokens=pm.input_tokens,
                output_tokens=pm.output_tokens,
                neurons=pm.neurons,
                estimated_cost_usd=pm.estimated_cost_usd,
                cost_status=pm.cost_status,
            )
        return LocalIntentResult(
            intent,
            resp.latency_ms,
            "ok",
            resp.model or model,
            provider=prov_used,
            input_tokens=pm.input_tokens,
            output_tokens=pm.output_tokens,
            neurons=pm.neurons,
            estimated_cost_usd=pm.estimated_cost_usd,
            cost_status=pm.cost_status,
        )
    except (ValueError, TypeError, AttributeError):
        return LocalIntentResult(
            None,
            resp.latency_ms,
            "invalid_response",
            model,
            provider=prov_used,
            input_tokens=pm.input_tokens,
            output_tokens=pm.output_tokens,
            neurons=pm.neurons,
            estimated_cost_usd=pm.estimated_cost_usd,
            cost_status=pm.cost_status,
        )
