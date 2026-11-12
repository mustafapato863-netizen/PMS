"""Scripted stand-in for the unified provider engine (Cloudflare primary, Gemini fallback).

Tests use this instead of any HTTP transport, so no test can reach a real
provider. Requests are captured in the OpenAI-style shape the older tests
asserted on: ``{"messages": [{"role": "system", ...}, {"role": "user", ...}], ...}``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from services.ai import provider_engine
from services.ai.provider_engine import ProviderAttempt, ProviderRequest, ProviderResponse

DEFAULT_MODEL = {"cloudflare": "@cf/ibm-granite/granite-4.0-h-micro", "gemini": "gemini-2.5-flash"}


def ok_response(content: str, provider: str = "cloudflare", model: str | None = None, latency_ms: float = 1.0) -> ProviderResponse:
    model = model or DEFAULT_MODEL[provider]
    return ProviderResponse(
        content=content,
        provider=provider,
        model=model,
        outcome="success",
        latency_ms=latency_ms,
        attempts=[ProviderAttempt(provider=provider, model=model, status="success", latency_ms=latency_ms)],
    )


def failed_response(outcome: str = "provider_unavailable", status: str = "transient_error") -> ProviderResponse:
    return ProviderResponse(
        content="",
        provider="none",
        model="none",
        outcome=outcome,
        latency_ms=1.0,
        attempts=[ProviderAttempt(provider="cloudflare", model=DEFAULT_MODEL["cloudflare"], status=status)],
    )


class ScriptedProviderEngine:
    """Replays ``replies`` in order, repeating the last one.

    Items may be dict/str/ProviderResponse, or a callable taking the captured request and returning one of those.
    """

    def __init__(self, replies: list[Any], provider: str = "cloudflare") -> None:
        if not replies:
            raise ValueError("at least one scripted reply is required")
        self.replies = list(replies)
        self.provider = provider
        self.calls = 0
        self.captured: list[dict[str, Any]] = []

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        messages: list[dict[str, str]] = []
        if request.system_instruction:
            messages.append({"role": "system", "content": request.system_instruction})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages if m.role != "system")
        self.captured.append(
            {
                "messages": messages,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "purpose": request.purpose,
                "json_schema": request.json_schema,
                "timeout_seconds": request.timeout_seconds,
            }
        )
        item = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        if callable(item):
            item = item(self.captured[-1])
        if isinstance(item, ProviderResponse):
            return item
        content = item if isinstance(item, str) else json.dumps(item)
        return ok_response(content, provider=self.provider)


def install_scripted_provider(
    monkeypatch: pytest.MonkeyPatch, replies: list[Any] | Any, provider: str = "cloudflare"
) -> list[dict[str, Any]]:
    """Make ``get_unified_provider_engine()`` return a scripted engine; returns the captured requests."""
    if not isinstance(replies, list):
        replies = [replies]
    engine = ScriptedProviderEngine(replies, provider=provider)
    monkeypatch.setattr(provider_engine, "_default_engine", engine)
    return engine.captured
