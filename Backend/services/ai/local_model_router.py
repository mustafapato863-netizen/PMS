"""Optional loopback-only intent suggestions; PMS remains the source of facts."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_intent_enabled() -> bool:
    return os.environ.get("PMS_AI_LOCAL_ROUTER_ENABLED", "false").strip().casefold() in {"1", "true", "yes", "on"}


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
    """Ask a local model for an intent only, never scores, identities or SQL.

    The result is an untrusted suggestion. The caller must verify completeness,
    enforce authorization and compute every answer through PMS services.
    """
    started = time.perf_counter()

    def result(intent: str | None, reason: str) -> LocalIntentResult:
        return LocalIntentResult(intent, round((time.perf_counter() - started) * 1000, 2), reason)

    if not local_intent_enabled():
        return result(None, "disabled")
    if not question or not question.strip() or len(question) > 600:
        return result(None, "invalid_question")
    url = os.environ.get("PMS_AI_LOCAL_ROUTER_URL", "http://127.0.0.1:18080/v1/chat/completions").strip()
    try:
        parsed = urllib.parse.urlsplit(url)
        # Do not turn an admin-configurable URL into an outbound network request.
        if parsed.scheme != "http" or parsed.username or parsed.password or not parsed.hostname:
            return result(None, "invalid_endpoint")
        if not ipaddress.ip_address(parsed.hostname).is_loopback:
            return result(None, "invalid_endpoint")
        if parsed.path != "/v1/chat/completions" or parsed.query or parsed.fragment:
            return result(None, "invalid_endpoint")
    except ValueError:
        return result(None, "invalid_endpoint")
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
    body = json.dumps(
        {
            "model": "local",
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": question.strip()},
            ],
            "temperature": 0,
            "max_tokens": 32,
            "response_format": {
                "type": "json_schema",
                "json_schema": build_intent_json_schema(),
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        timeout = min(30.0, max(0.5, float(os.environ.get("PMS_AI_LOCAL_ROUTER_TIMEOUT_SECONDS", "6.0"))))
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            return result(None, "response_too_large")
        envelope = json.loads(raw)
        content = envelope["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            return result(None, "invalid_response")
        cleaned = _JSON_FENCE_RE.sub("", content.strip()).strip()
        suggestion = json.loads(cleaned)
        if not isinstance(suggestion, dict) or set(suggestion) != {"intent"}:
            return result(None, "invalid_response")
        intent = suggestion["intent"]
        if not isinstance(intent, str) or intent not in ALLOWED_INTENTS:
            return result(None, "invalid_intent")
        return result(intent, "ok")
    except TimeoutError:
        return result(None, "timeout")
    except (ValueError, TypeError, KeyError, IndexError, OSError, urllib.error.URLError):
        return result(None, "unavailable_or_invalid")
