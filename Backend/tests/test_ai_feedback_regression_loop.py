"""Focused PR 4 regression tests: feedback survey separation, dedup/response rate, review routes, and de-identified regression templates."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import ai_corrective_actions, ai_workspace
from config.database import Base, get_db
from models.models import AiInteractionTrace, Employee, Team
from services.ai import feature_gate


def _make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _build_client(db, monkeypatch):
    monkeypatch.setattr(feature_gate, "is_ai_enabled", lambda _db: True)
    monkeypatch.setattr(feature_gate, "read_ai_corrective_action_pilot_enabled", lambda _db: True)

    app = FastAPI()

    @app.middleware("http")
    async def inject_identity(request: Request, call_next):
        role = request.headers.get("x-test-role", "Admin")
        user_id = request.headers.get("x-test-user-id", "u-admin-1")
        request.state.user = {"role": role, "user_id": user_id}
        return await call_next(request)

    def _scope(_db, request: Request):
        user = getattr(request.state, "user", None)
        if isinstance(user, dict):
            return user
        return {"role": "Admin", "user_id": "u-admin-1"}

    monkeypatch.setattr(ai_workspace, "require_authenticated_scope", _scope)
    monkeypatch.setattr(ai_corrective_actions, "require_authenticated_scope", _scope)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.include_router(ai_workspace.router, prefix="/api")
    app.include_router(ai_corrective_actions.router, prefix="/api")
    return TestClient(app)


def test_feedback_clusters_response_rate_language_model_and_dedup(monkeypatch):
    db = _make_session()
    try:
        t1 = uuid.uuid4()
        t2 = uuid.uuid4()
        t_unsurveyed = uuid.uuid4()
        db.add_all(
            [
                AiInteractionTrace(
                    id=t1,
                    user_id="user-1",
                    role="Admin",
                    prompt="نادية فاضل Waiting Time و overall PMS في سبتمبر",
                    sanitized_prompt="Employee Waiting Time و overall PMS في سبتمبر",
                    provider_name="cloudflare",
                    model_name="@cf/ibm-granite/granite-4.0-h-micro",
                    non_empty_evidence=True,
                    feedback_rating="down",
                    feedback_reason="incomplete_response",
                    session_state={"team": "Pharmacy", "region": "UAE"},
                    tool_digest={
                        "feedback_governance": {
                            "surface": "workspace_chat",
                            "language": "mixed",
                            "model_version": "@cf/ibm-granite/granite-4.0-h-micro",
                            "operation_family": "compound_query",
                            "scope_team": "Pharmacy",
                            "reason_tag": "incomplete_response",
                        }
                    },
                    structured_response={"outcome": "answer", "intent": "current_value"},
                    created_at=datetime.now(timezone.utc),
                ),
                AiInteractionTrace(
                    id=t2,
                    user_id="user-2",
                    role="Manager",
                    prompt="Draft corrective action for Inbound Booking Rate",
                    sanitized_prompt="Draft corrective action for Inbound Booking Rate",
                    provider_name="nvidia",
                    model_name="nvidia/nemotron-3.5-super-vl-120b-a12b",
                    non_empty_evidence=True,
                    feedback_rating="down",
                    feedback_reason="incorrect_kpi_interpretation",
                    session_state={"team": "Inbound", "region": "EGY"},
                    tool_digest={
                        "feedback_governance": {
                            "surface": "corrective_action_pilot",
                            "language": "en",
                            "model_version": "nvidia/nemotron-3.5-super-vl-120b-a12b",
                            "operation_family": "corrective_action_draft",
                            "scope_team": "Inbound",
                            "reason_tag": "incorrect_kpi_interpretation",
                        }
                    },
                    structured_response={"outcome": "draft_rejected", "intent": "corrective_action_draft"},
                    created_at=datetime.now(timezone.utc),
                ),
                AiInteractionTrace(
                    id=t_unsurveyed,
                    user_id="user-3",
                    role="Admin",
                    prompt="Inbound score in September 2026?",
                    sanitized_prompt="Inbound score in September 2026?",
                    provider_name="deterministic",
                    model_name="pms-local-router-v1",
                    non_empty_evidence=True,
                    feedback_rating=None,
                    tool_digest={"feedback_governance": {"surface": "workspace_chat"}},
                    structured_response={"outcome": "answer"},
                    created_at=datetime.now(timezone.utc),
                ),
            ]
        )
        db.commit()

        client = _build_client(db, monkeypatch)
        res = client.get("/api/ai/feedback/clusters", headers={"x-test-role": "Admin"})
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["total_interactions_sampled"] >= 3
        assert data["survey_response_rate_pct"] is not None
        assert 50.0 <= data["survey_response_rate_pct"] <= 100.0
        clusters = data["clusters"]
        assert len(clusters) >= 2

        chat_cluster = next(
            c for c in clusters if c["surface"] == "workspace_chat" and c["operation_family"] == "compound_query"
        )
        assert chat_cluster["language"] == "mixed"
        assert chat_cluster["model_version"] == "@cf/ibm-granite/granite-4.0-h-micro"
        assert chat_cluster["distinct_traces"] == 1
        assert chat_cluster["response_rate_pct"] is not None

        ca_cluster = next(c for c in clusters if c["surface"] == "corrective_action_pilot")
        assert ca_cluster["reason_tag"] == "incorrect_kpi_interpretation"
    finally:
        db.close()


def test_review_route_and_deidentified_regression_template_endpoint(monkeypatch):
    db = _make_session()
    try:
        team = Team(id=uuid.uuid4(), name="pharmacy", db_name="Pharmacy", display_name="Pharmacy", region="UAE", is_active=True)
        db.add(team)
        db.flush()
        db.add(
            Employee(
                id=uuid.uuid4(),
                employee_id="EMP701",
                name="Nadia Fadel",
                team_id=team.id,
                region="UAE",
                performance_level="Employee",
                is_active=True,
            )
        )
        trace_id = uuid.uuid4()
        db.add(
            AiInteractionTrace(
                id=trace_id,
                user_id="user-9",
                role="Admin",
                prompt="September Nadia Fadel Waiting Time and overall PMS",
                sanitized_prompt="September Nadia Fadel Waiting Time and overall PMS",
                provider_name="deterministic",
                non_empty_evidence=True,
                feedback_rating="down",
                feedback_reason="incomplete_response",
                session_state={"team": "Pharmacy", "region": "UAE"},
                tool_digest={
                    "feedback_governance": {
                        "surface": "workspace_chat",
                        "language": "en",
                        "operation_family": "compound_query",
                        "scope_team": "Pharmacy",
                        "scope_country": "UAE",
                        "reason_tag": "incomplete_response",
                    }
                },
                structured_response={"outcome": "answer", "intent": "current_value"},
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        client = _build_client(db, monkeypatch)
        rev = client.post(
            f"/api/ai/traces/{trace_id}/review",
            headers={"x-test-role": "Admin"},
            json={
                "decision": "rejected",
                "review_route": "rendering",
                "reviewer_usability": "not_usable",
                "proposed_action": "Ensure all requested KPI parts render together.",
                "review_notes": "Dropped overall score sentence.",
            },
        )
        assert rev.status_code == 200, rev.text
        rev_data = rev.json()
        assert rev_data["review_status"] == "rejected"

        tmpl_res = client.get(
            f"/api/ai/feedback/traces/{trace_id}/regression-template",
            headers={"x-test-role": "Admin"},
        )
        assert tmpl_res.status_code == 200, tmpl_res.text
        tmpl = tmpl_res.json()
        assert tmpl["trace_id"] == str(trace_id)
        assert tmpl["review_route"] == "rendering"
        assert tmpl["revert_path"] == "PMS_AI_COMPOUND_PARTS_ENABLED=false"
        # Employee PII must be redacted before building regression scaffold
        assert "Nadia" not in tmpl["sanitized_prompt"]
        assert "EMP701" not in tmpl["unseen_variation_prompt_template"]

        # Non-Admin denied
        denied = client.get(
            f"/api/ai/feedback/traces/{trace_id}/regression-template",
            headers={"x-test-role": "Manager"},
        )
        assert denied.status_code == 403
    finally:
        db.close()
