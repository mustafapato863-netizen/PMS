from __future__ import annotations

import json
import pytest

from services.ai.local_data_explorer import (
    _call_local_exploration_model,
    _compose_grounded_answer,
    _last_exploration_provider,
    validate_grounded_synthesis,
)
from services.ai.provider_engine import (
    ProviderAttempt,
    ProviderRequest,
    ProviderResponse,
)


class MockUnifiedEngine:
    def __init__(self, response: ProviderResponse) -> None:
        self.response = response
        self.last_request: ProviderRequest | None = None

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.last_request = request
        return self.response


def test_exploration_planner_uses_gemini_via_unified_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_UNIFIED_EXPLORER", "true")

    step_json = json.dumps(
        {
            "action": "call_tools",
            "unknown_code": "none",
            "tools": [{"tool": "get_team_score_summary", "team": "Inbound", "period": "2026-09"}],
        }
    )
    mock_resp = ProviderResponse(
        content=step_json,
        provider="gemini",
        model="gemini-2.5-flash",
        outcome="success",
        latency_ms=120.0,
        attempts=[ProviderAttempt(provider="gemini", model="gemini-2.5-flash", status="success", latency_ms=120.0)],
    )
    mock_engine = MockUnifiedEngine(mock_resp)
    monkeypatch.setattr(
        "services.ai.local_data_explorer.get_unified_provider_engine",
        lambda: mock_engine,
    )

    parsed, ms, status = _call_local_exploration_model(
        question="How did Inbound perform in September 2026?",
        step=1,
        max_steps=2,
        active_context={"team": "Inbound", "period": "2026-09"},
        authorized_concepts={"authorized_teams": ["Inbound"], "latest_published_period": "2026-09", "published_periods": ["2026-09"]},
        collected_evidence=[],
    )

    assert status == "ok"
    assert parsed is not None
    assert parsed["action"] == "call_tools"
    assert len(parsed["tools"]) == 1
    assert parsed["tools"][0]["tool"] == "get_team_score_summary"
    assert _last_exploration_provider.get() == "gemini"
    assert mock_engine.last_request is not None
    assert mock_engine.last_request.purpose == "exploration"


def test_exploration_planner_falls_back_to_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_UNIFIED_EXPLORER", "true")

    step_json = json.dumps(
        {
            "action": "finish",
            "unknown_code": "none",
            "tools": [],
        }
    )
    mock_resp = ProviderResponse(
        content=step_json,
        provider="gemini",
        model="gemini-2.5-flash",
        outcome="fallback_success",
        latency_ms=250.0,
        attempts=[
            ProviderAttempt(provider="cloudflare", model="@cf/ibm-granite/granite-4.0-h-micro", status="transient_error", latency_ms=100.0),
            ProviderAttempt(provider="gemini", model="gemini-2.5-flash", status="success", latency_ms=150.0),
        ],
    )
    mock_engine = MockUnifiedEngine(mock_resp)
    monkeypatch.setattr(
        "services.ai.local_data_explorer.get_unified_provider_engine",
        lambda: mock_engine,
    )

    parsed, ms, status = _call_local_exploration_model(
        question="Finish checking Inbound",
        step=2,
        max_steps=2,
        active_context={"team": "Inbound", "period": "2026-09"},
        authorized_concepts={"authorized_teams": ["Inbound"], "latest_published_period": "2026-09", "published_periods": ["2026-09"]},
        collected_evidence=[],
    )

    assert status == "ok"
    assert parsed is not None
    assert parsed["action"] == "finish"
    assert _last_exploration_provider.get() == "gemini"


def test_exploration_synthesis_uses_gemini_via_unified_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_UNIFIED_EXPLORER", "true")

    syn_json = json.dumps(
        {
            "fact_ids": ["F1"],
            "headline": "Inbound achieved an average score of 82.5% in September 2026.",
        }
    )
    mock_resp = ProviderResponse(
        content=syn_json,
        provider="gemini",
        model="gemini-2.5-flash",
        outcome="success",
        latency_ms=110.0,
        attempts=[ProviderAttempt(provider="gemini", model="gemini-2.5-flash", status="success", latency_ms=110.0)],
    )
    mock_engine = MockUnifiedEngine(mock_resp)
    monkeypatch.setattr(
        "services.ai.local_data_explorer.get_unified_provider_engine",
        lambda: mock_engine,
    )

    fact_ledger = [
        {
            "fact_id": "F1",
            "part": "score",
            "subject": "Inbound",
            "period": "September 2026",
            "value": 82.5,
            "display": "82.5%",
            "unit": "%",
        }
    ]

    headline, ms, status = _compose_grounded_answer(
        question="How did Inbound perform in September 2026?",
        fact_ledger=fact_ledger,
    )

    assert status == "ok"
    assert headline == "Inbound achieved an average score of 82.5% in September 2026."
    assert _last_exploration_provider.get() == "gemini"
    assert mock_engine.last_request is not None
    assert mock_engine.last_request.purpose == "exploration_synthesis"


def test_exploration_synthesis_rejects_hallucinated_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_UNIFIED_EXPLORER", "true")

    # The model attempts to hallucinate 99.9% which is not in the fact ledger
    syn_json = json.dumps(
        {
            "fact_ids": ["F1"],
            "headline": "Inbound achieved 99.9% in September 2026.",
        }
    )
    mock_resp = ProviderResponse(
        content=syn_json,
        provider="gemini",
        model="gemini-2.5-flash",
        outcome="success",
        latency_ms=110.0,
        attempts=[ProviderAttempt(provider="gemini", model="gemini-2.5-flash", status="success", latency_ms=110.0)],
    )
    mock_engine = MockUnifiedEngine(mock_resp)
    monkeypatch.setattr(
        "services.ai.local_data_explorer.get_unified_provider_engine",
        lambda: mock_engine,
    )

    fact_ledger = [
        {
            "fact_id": "F1",
            "part": "score",
            "subject": "Inbound",
            "period": "September 2026",
            "value": 82.5,
            "display": "82.5%",
            "unit": "%",
        }
    ]

    headline, ms, status = _compose_grounded_answer(
        question="How did Inbound perform in September 2026?",
        fact_ledger=fact_ledger,
    )

    assert headline is None
    assert status in ("missing_fact_value", "unverified_number")


def test_no_model_configured_returns_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_UNIFIED_EXPLORER", "true")

    mock_resp = ProviderResponse(
        content=None,
        provider=None,
        model=None,
        outcome="no_model_configured",
        latency_ms=5.0,
        attempts=[ProviderAttempt(provider="gemini", model="gemini-2.5-flash", status="missing_key", latency_ms=0.0)],
    )
    mock_engine = MockUnifiedEngine(mock_resp)
    monkeypatch.setattr(
        "services.ai.local_data_explorer.get_unified_provider_engine",
        lambda: mock_engine,
    )

    parsed, ms, status = _call_local_exploration_model(
        question="How did Inbound perform?",
        step=1,
        max_steps=2,
        active_context={"team": "Inbound", "period": "2026-09"},
        authorized_concepts={"authorized_teams": ["Inbound"], "latest_published_period": "2026-09", "published_periods": ["2026-09"]},
        collected_evidence=[],
    )

    assert parsed is None
    assert status == "no_model_configured"


def test_no_legacy_transport_remains_and_flag_is_not_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """The unified provider engine is the only path, with or without PMS_AI_UNIFIED_EXPLORER."""
    import services.ai.local_data_explorer as explorer

    monkeypatch.delenv("PMS_AI_UNIFIED_EXPLORER", raising=False)
    assert not hasattr(explorer, "chat_completion")
    assert not hasattr(explorer, "_ORIGINAL_CHAT_COMPLETION")

    mock_engine = MockUnifiedEngine(
        ProviderResponse(
            content=json.dumps({"action": "finish", "unknown_code": "none", "tools": []}),
            provider="cloudflare",
            model="@cf/ibm-granite/granite-4.0-h-micro",
            outcome="success",
            latency_ms=45.0,
            attempts=[ProviderAttempt(provider="cloudflare", model="@cf/ibm-granite/granite-4.0-h-micro", status="success")],
        )
    )
    monkeypatch.setattr("services.ai.local_data_explorer.get_unified_provider_engine", lambda: mock_engine)

    parsed, ms, status = _call_local_exploration_model(
        question="Finish exploring",
        step=1,
        max_steps=2,
        active_context={"team": "Inbound", "period": "2026-09"},
        authorized_concepts={"authorized_teams": ["Inbound"], "latest_published_period": "2026-09", "published_periods": ["2026-09"]},
        collected_evidence=[],
    )

    assert status == "ok"
    assert parsed is not None
    assert parsed["action"] == "finish"
    assert _last_exploration_provider.get() == "cloudflare"


def test_run_bounded_exploration_reports_unified_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from models.ai_schemas import SessionFilterContext
    from services.ai.local_data_explorer import run_bounded_exploration
    from tests.test_local_assistant_exploration import (
        _build_in_memory_db,
        _make_call_center_record,
        _patch_records,
    )

    monkeypatch.setenv("PMS_AI_UNIFIED_EXPLORER", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_SYNTHESIS_ENABLED", "false")

    records = [
        _make_call_center_record("EMP001", "Alice", "Inbound", 85.0, 10, 30, 30, 80, month="September"),
    ]
    _patch_records(monkeypatch, records)

    step_responses = [
        ProviderResponse(
            content=json.dumps(
                {
                    "action": "call_tools",
                    "unknown_code": "none",
                    "tools": [{"tool": "get_team_score_summary", "team": "Inbound", "period": "2026-09"}],
                }
            ),
            provider="gemini",
            model="gemini-2.5-flash",
            outcome="success",
            latency_ms=100.0,
        ),
        ProviderResponse(
            content=json.dumps({"action": "finish", "unknown_code": "none", "tools": []}),
            provider="gemini",
            model="gemini-2.5-flash",
            outcome="success",
            latency_ms=80.0,
        ),
    ]

    class SequenceEngine:
        def __init__(self, responses: list[ProviderResponse]):
            self.responses = list(responses)
            self.calls = 0

        def generate(self, request: ProviderRequest) -> ProviderResponse:
            resp = self.responses[min(self.calls, len(self.responses) - 1)]
            self.calls += 1
            return resp

    engine = SequenceEngine(step_responses)
    monkeypatch.setattr(
        "services.ai.local_data_explorer.get_unified_provider_engine",
        lambda: engine,
    )

    with _build_in_memory_db() as db:
        res = run_bounded_exploration(
            db=db,
            scope={"role": "Admin", "has_unrestricted_team_access": True},
            prompt="How did Inbound perform in September 2026?",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
            published_periods={"2026-09"},
            employee_candidates=[],
        )

    assert res.handled is True
    assert res.provider_calls >= 1
    assert res.provider_used == "gemini"
    assert res.provider_name == "gemini"
    assert res.model_name == "gemini-2.5-flash"


def test_orchestrator_turn_reports_gemini_when_unified_exploration_active(monkeypatch: pytest.MonkeyPatch) -> None:
    from models.ai_schemas import AiChatRequest, SessionFilterContext
    from services.ai.orchestrator import PmsAiOrchestrator
    from tests.test_local_assistant_exploration import (
        _build_in_memory_db,
        _make_call_center_record,
        _patch_records,
    )

    monkeypatch.setenv("PMS_AI_UNIFIED_EXPLORER", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_SYNTHESIS_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")

    records = [
        _make_call_center_record("EMP001", "Alice", "Inbound", 85.0, 10, 30, 30, 80, month="September"),
    ]
    _patch_records(monkeypatch, records)

    step_responses = [
        ProviderResponse(
            content=json.dumps(
                {
                    "action": "call_tools",
                    "unknown_code": "none",
                    "tools": [{"tool": "get_team_score_summary", "team": "Inbound", "period": "2026-09"}],
                }
            ),
            provider="gemini",
            model="gemini-2.5-flash",
            outcome="success",
            latency_ms=90.0,
        ),
        ProviderResponse(
            content=json.dumps({"action": "finish", "unknown_code": "none", "tools": []}),
            provider="gemini",
            model="gemini-2.5-flash",
            outcome="success",
            latency_ms=70.0,
        ),
    ]

    class SequenceEngine:
        def __init__(self, responses: list[ProviderResponse]):
            self.responses = list(responses)
            self.calls = 0

        def generate(self, request: ProviderRequest) -> ProviderResponse:
            resp = self.responses[min(self.calls, len(self.responses) - 1)]
            self.calls += 1
            return resp

    monkeypatch.setattr(
        "services.ai.local_data_explorer.get_unified_provider_engine",
        lambda: SequenceEngine(step_responses),
    )

    with _build_in_memory_db() as db:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "has_unrestricted_team_access": True})
        resp = orch.run_chat_turn(
            AiChatRequest(
                prompt="How did Inbound perform in September 2026?",
                session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
            )
        )

    assert resp.outcome == "answer"
    assert resp.provider_used == "gemini"
    assert resp.model_used == "gemini-2.5-flash"


