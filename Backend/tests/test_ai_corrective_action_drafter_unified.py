"""Tests for Phase 3: CorrectiveActionDrafter Integration with UnifiedProviderEngine.

Verifies:
1. Gemini succeeds as primary provider, returning validated suggestion with provider_used="gemini".
2. Gemini rate limit or transient failure automatically falls back to OpenAI with provider_used="openai".
3. Gemini safety refusal terminates immediately without OpenAI fallback.
4. Closed vocabulary validator strictly blocks model hallucinations, causes, and digits from both providers.
5. Insufficient evidence never calls either AI provider.
6. End-to-end API router flow succeeds under Admin pilot gating with provider provenance intact.
"""

from __future__ import annotations

import datetime
import json
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import ai_corrective_actions
from config.database import Base, get_db
from models.ai_schemas import (
    AiCorrectiveActionSuggestionDraft,
    AiCorrectiveActionSuggestionPayload,
    AiCorrectiveActionSuggestionRequest,
)
from models.models import Action, Employee, KPIValue, PerformanceRecord, Team
from services.ai import feature_gate
from services.ai.corrective_action_drafter import CorrectiveActionDrafter
from services.ai.provider_engine import (
    GeminiProviderAdapter,
    OpenAIProviderAdapter,
    ProviderRateLimitError,
    ProviderSafetyRefusalError,
    TokenUsage,
    UnifiedProviderConfig,
    UnifiedProviderEngine,
)

ADMIN_SCOPE = {"role": "Admin", "user_id": "admin-1"}
ADMIN_HEADERS = {"X-User-Role": "Admin"}
URL = "/api/ai/corrective-action-suggestions"


# ---------------------------------------------------------------------------
# Fixtures & Test Database
# ---------------------------------------------------------------------------


def _make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _employee_with_kpis(db, *, employee_id="EMP-1", name="Sara Inbound", team_name="Inbound"):
    team = db.query(Team).filter(Team.display_name == team_name).one_or_none()
    if team is None:
        team = Team(
            id=uuid.uuid4(), name=team_name.casefold(), db_name=team_name, display_name=team_name,
            region="EGY", team_level="employee", is_active=True,
        )
        db.add(team)
        db.flush()

    employee = Employee(
        id=uuid.uuid4(), employee_id=employee_id, name=name, team_id=team.id,
        region="EGY", performance_level="Employee", position_name="Agent", is_active=True,
    )
    db.add(employee)
    db.flush()

    record = PerformanceRecord(
        id=uuid.uuid4(), employee_id=employee.id, team_id=team.id, month="September", year=2026,
        performance_level="Employee", position_name="Agent", region="EGY", branch_key=None,
        score=70.0, grade="C", status="Below",
    )
    db.add(record)
    db.flush()

    # bookings: 30/40 (75%), upsell: 0/10 (0% - focus KPI)
    db.add(KPIValue(
        record_id=record.id, record_year=2026, kpi_key="bookings_count", actual_value=30.0,
        target_value=40.0, achievement_ratio=0.75, weight_applied=0.5, contribution=0.375,
    ))
    db.add(KPIValue(
        record_id=record.id, record_year=2026, kpi_key="upsell", actual_value=0.0,
        target_value=10.0, achievement_ratio=0.0, weight_applied=0.2, contribution=0.0,
    ))
    db.flush()

    db.add(Action(
        id=uuid.uuid4(), employee_id=employee.id, team_id=team.id, branch_key=None,
        month="September", year=2026, action_type="Coaching",
        action_text="Coach on talk tracks", status="Open", linked_kpi_key="bookings_count",
        created_at=datetime.datetime(2026, 9, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
    ))
    db.commit()
    return team, employee


@pytest.fixture
def db():
    session = _make_db()
    _employee_with_kpis(session)
    yield session
    session.close()


@pytest.fixture
def mock_gemini():
    return MagicMock(spec=GeminiProviderAdapter)


@pytest.fixture
def mock_openai():
    return MagicMock(spec=OpenAIProviderAdapter)


@pytest.fixture
def engine_config():
    return UnifiedProviderConfig(
        gemini_enabled=True,
        openai_enabled=True,
        fallback_enabled=True,
        gemini_model="gemini-2.5-flash",
        openai_model="gpt-4o-mini",
        timeout_seconds=5.0,
        max_retries=1,
        gemini_api_key="valid-gemini-key",
        openai_api_key="valid-openai-key",
    )


@pytest.fixture
def unified_engine(engine_config, mock_gemini, mock_openai):
    return UnifiedProviderEngine(
        config=engine_config,
        gemini_adapter=mock_gemini,
        openai_adapter=mock_openai,
    )


def _request_body():
    return {
        "team": "Inbound",
        "month": "September",
        "year": 2026,
        "performance_level": "Employee",
        "employee_id": "EMP-1",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_drafter_gemini_primary_success(db, unified_engine, mock_gemini, mock_openai):
    """When Gemini returns a valid, grounded suggestion, drafter uses Gemini and never calls OpenAI."""
    gemini_json = json.dumps({
        "focus_kpi_key": "upsell",
        "action_type": "Coaching",
        "steps": [
            "Review recent calls with missed upsell opportunities.",
            "Hold a short coaching session on upsell talk tracks.",
        ],
    })
    mock_gemini.execute.return_value = (
        gemini_json,
        TokenUsage(prompt_tokens=150, completion_tokens=30, total_tokens=180),
    )

    drafter = CorrectiveActionDrafter(db, provider_engine=unified_engine)
    req = AiCorrectiveActionSuggestionRequest(**_request_body())
    payload = drafter.suggest(user_scope=ADMIN_SCOPE, request=req)

    assert payload.outcome == "suggested"
    assert payload.provider_used == "gemini"
    assert payload.model_called is True
    assert payload.model_version == "gemini-2.5-flash"
    assert payload.draft is not None
    assert payload.draft.action_type == "Coaching"
    assert payload.draft.focus_kpi_key == "upsell"
    assert payload.draft.recommended_steps_source == "gemini"
    assert len(payload.draft.recommended_steps) == 2
    assert "Review recent calls" in payload.draft.recommended_steps[0]

    # OpenAI must NOT have been called
    mock_gemini.execute.assert_called_once()
    mock_openai.execute.assert_not_called()


def test_drafter_openai_fallback_on_gemini_rate_limit(db, unified_engine, mock_gemini, mock_openai):
    """When Gemini is rate-limited (HTTP 429), drafter seamlessly falls back to OpenAI with provider_used='openai'."""
    mock_gemini.execute.side_effect = ProviderRateLimitError("Gemini quota exceeded", http_code=429)

    openai_json = json.dumps({
        "focus_kpi_key": "upsell",
        "action_type": "Training",
        "steps": [
            "Schedule a short training module on upsell processes.",
        ],
    })
    mock_openai.execute.return_value = (
        openai_json,
        TokenUsage(prompt_tokens=150, completion_tokens=25, total_tokens=175),
    )

    drafter = CorrectiveActionDrafter(db, provider_engine=unified_engine)
    req = AiCorrectiveActionSuggestionRequest(**_request_body())
    payload = drafter.suggest(user_scope=ADMIN_SCOPE, request=req)

    assert payload.outcome == "suggested"
    assert payload.provider_used == "openai"
    assert payload.model_called is True
    assert payload.model_version == "gpt-4o-mini"
    assert payload.draft is not None
    assert payload.draft.action_type == "Training"
    assert payload.draft.recommended_steps_source == "openai"
    assert len(payload.draft.recommended_steps) == 1

    # Both were called: Gemini once (rate limited), then OpenAI fallback
    mock_gemini.execute.assert_called_once()
    mock_openai.execute.assert_called_once()


def test_drafter_gemini_safety_refusal_terminal_no_fallback(db, unified_engine, mock_gemini, mock_openai):
    """Safety refusals from Gemini are terminal: OpenAI fallback is forbidden, returning model_unavailable."""
    mock_gemini.execute.side_effect = ProviderSafetyRefusalError("Prompt blocked due to SAFETY")

    drafter = CorrectiveActionDrafter(db, provider_engine=unified_engine)
    req = AiCorrectiveActionSuggestionRequest(**_request_body())
    payload = drafter.suggest(user_scope=ADMIN_SCOPE, request=req)

    assert payload.outcome == "model_unavailable"
    assert payload.provider_used == "none"
    assert payload.draft is None
    assert payload.model_called is True
    assert payload.fallback_reason == "safety_refusal"

    # OpenAI must NOT have been called to bypass safety policy
    mock_gemini.execute.assert_called_once()
    mock_openai.execute.assert_not_called()


def test_drafter_closed_vocabulary_rejects_hallucinations(db, unified_engine, mock_gemini, mock_openai):
    """Steps containing unauthorized causes ('lacks knowledge') are strictly rejected by the validator."""
    hallucinated_json = json.dumps({
        "focus_kpi_key": "upsell",
        "action_type": "Coaching",
        "steps": [
            "Coach the agent because she lacks product knowledge.",
        ],
    })
    mock_gemini.execute.return_value = (
        hallucinated_json,
        TokenUsage(prompt_tokens=150, completion_tokens=20, total_tokens=170),
    )

    drafter = CorrectiveActionDrafter(db, provider_engine=unified_engine)
    req = AiCorrectiveActionSuggestionRequest(**_request_body())
    payload = drafter.suggest(user_scope=ADMIN_SCOPE, request=req)

    assert payload.outcome == "draft_rejected"
    assert payload.draft is None
    assert payload.fallback_reason == "validation_failed"
    assert len(payload.validation_errors) > 0


def test_drafter_closed_vocabulary_rejects_digits_and_numbers(db, unified_engine, mock_gemini, mock_openai):
    """Steps containing digits or numerical targets are strictly rejected."""
    digits_json = json.dumps({
        "focus_kpi_key": "upsell",
        "action_type": "Coaching",
        "steps": [
            "Increase upsell attempts by 20 percent weekly.",
        ],
    })
    mock_gemini.execute.return_value = (
        digits_json,
        TokenUsage(prompt_tokens=150, completion_tokens=20, total_tokens=170),
    )

    drafter = CorrectiveActionDrafter(db, provider_engine=unified_engine)
    req = AiCorrectiveActionSuggestionRequest(**_request_body())
    payload = drafter.suggest(user_scope=ADMIN_SCOPE, request=req)

    assert payload.outcome == "draft_rejected"
    assert payload.draft is None
    assert payload.fallback_reason == "validation_failed"
    assert any("number" in err for err in payload.validation_errors)


def test_drafter_insufficient_evidence_never_calls_provider(db, unified_engine, mock_gemini, mock_openai):
    """When evidence is insufficient (e.g. unknown requested linked KPI), providers are never called."""
    drafter = CorrectiveActionDrafter(db, provider_engine=unified_engine)
    req = AiCorrectiveActionSuggestionRequest(
        team="Inbound",
        month="September",
        year=2026,
        performance_level="Employee",
        employee_id="EMP-1",
        linked_kpi_key="non_existent_kpi_key",
    )
    payload = drafter.suggest(user_scope=ADMIN_SCOPE, request=req)

    assert payload.outcome == "insufficient_evidence"
    assert payload.model_called is False
    assert payload.provider_used == "none"
    mock_gemini.execute.assert_not_called()
    mock_openai.execute.assert_not_called()


def test_api_endpoint_end_to_end_with_gemini(db, unified_engine, mock_gemini, mock_openai, monkeypatch):
    """API router returns 200 with data.provider_used='gemini' and validated draft under Admin pilot."""
    feature_gate.set_ai_corrective_action_pilot_enabled(db, True, None)

    gemini_json = json.dumps({
        "focus_kpi_key": "upsell",
        "action_type": "Coaching",
        "steps": [
            "Review recent calls with missed upsell opportunities.",
        ],
    })
    mock_gemini.execute.return_value = (
        gemini_json,
        TokenUsage(prompt_tokens=150, completion_tokens=20, total_tokens=170),
    )

    # Patch global engine in provider_engine to use our mock-backed unified_engine
    import services.ai.provider_engine as pe
    monkeypatch.setattr(pe, "_default_engine", unified_engine)

    app = FastAPI()
    app.include_router(ai_corrective_actions.router, prefix="/api")

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(ai_corrective_actions, "require_authenticated_scope", lambda _db, _request: dict(ADMIN_SCOPE))

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(URL, json=_request_body(), headers=ADMIN_HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["outcome"] == "suggested"
    assert data["data"]["provider_used"] == "gemini"
    assert data["data"]["model_version"] == "gemini-2.5-flash"
    assert data["data"]["draft"]["action_type"] == "Coaching"
    assert data["data"]["draft"]["recommended_steps_source"] == "gemini"
    assert len(data["data"]["draft"]["recommended_steps"]) == 1
