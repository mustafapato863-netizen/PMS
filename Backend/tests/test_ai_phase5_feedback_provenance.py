"""Phase 5 checks for answer-bound feedback, provenance, and idempotency."""
from __future__ import annotations

import json
import uuid

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import ai_workspace
from config.database import Base, get_db
from models.ai_schemas import AiPilotFeedbackRequest
from models.models import AiInteractionTrace, AuditLog
from services.ai.feedback_service import (
    FeedbackGovernanceService,
    FeedbackIdempotencyConflictError,
)
from services.ai.trace_logger import TraceOwnershipError


def _make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _build_client(db, monkeypatch) -> TestClient:
    app = FastAPI()

    @app.middleware("http")
    async def inject_identity(request: Request, call_next):
        request.state.user = {
            "role": request.headers.get("x-test-role", "Manager"),
            "user_id": request.headers.get("x-test-user-id", "manager-1"),
        }
        return await call_next(request)

    def scope(_db, request: Request):
        return request.state.user

    monkeypatch.setattr(ai_workspace, "require_authenticated_scope", scope)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.include_router(ai_workspace.router, prefix="/api")
    return TestClient(app)


def _seed_trace(db, *, user_id: str = "manager-1") -> AiInteractionTrace:
    row = AiInteractionTrace(
        id=uuid.uuid4(),
        turn_id="synthetic-turn-001",
        user_id=user_id,
        role="Manager",
        prompt="Synthetic employee prompt with Nadia Fadel",
        sanitized_prompt="What is the Waiting Time? <EMPLOYEE_NAME>",
        session_state={"team": "Inbound", "region": "EGY", "performance_level": "Employee"},
        tool_calls=[{"tool_name": "read_employee_metric"}],
        tool_digest={"record_count": 1},
        structured_response={
            "headline": "Synthetic answer with 6.2 min",
            "narrative_bullets": ["September 2026: 6.2 min"],
            "typed_evidence": [
                {
                    "metric_id": "inbound:waitingtime",
                    "kpi_key": "waitingtime",
                    "display_name": "Waiting Time",
                    "team": "Inbound",
                    "period": "September 2026",
                    "actual": 6.2,
                    "unit": "min",
                    "employee_id": "SYNTH001",
                    "employee_name": "Nadia Fadel",
                    "source_link": "/employee/SYNTH001?month=September&year=2026",
                }
            ],
            "structured_query": {"team": "Inbound", "intent": "current_value"},
            "resolved_session_state": {
                "team": "Inbound",
                "region": "EGY",
                "performance_level": "Employee",
            },
            "provider_usage": {"fallback_outcome": "none"},
            "answer_source": "model_synthesis",
            "evidence_revision": "synthetic-revision-7",
            "prompt_version": "phase5-test-prompt-v1",
        },
        provider_name="synthetic-provider",
        model_name="synthetic-model-v1",
        latency_ms=25,
        non_empty_evidence=True,
        guardrail_triggered=False,
        is_distillation_eligible=False,
        reviewer_verified=False,
    )
    db.add(row)
    db.commit()
    return row


def test_workspace_feedback_is_trace_bound_hashed_and_idempotent(monkeypatch):
    db = _make_session()
    row = _seed_trace(db)
    client = _build_client(db, monkeypatch)
    payload = {
        "trace_id": str(row.id),
        "rating": "down",
        "category": "incorrect_answer",
        "reason": "The returned value needs review.",
        "idempotency_key": "feedback-submit-001",
        # Extra client metadata must not replace trace provenance.
        "provider_name": "client-invented-provider",
        "scope_team": "client-invented-team",
    }
    headers = {"x-test-role": "Admin", "x-test-user-id": "manager-1"}

    first = client.post("/api/ai/feedback", json=payload, headers=headers)
    second = client.post("/api/ai/feedback", json=payload, headers=headers)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert first.json()["reviewer_verified"] is False
    assert first.json()["is_distillation_eligible"] is False

    db.refresh(row)
    assert row.feedback_rating == "down"
    assert row.reviewer_verified is False
    assert row.reviewer_id is None
    governance = row.tool_digest["feedback_governance"]
    provenance = governance["answer_provenance"]
    assert provenance["provider_name"] == "synthetic-provider"
    assert provenance["model_version"] == "synthetic-model-v1"
    assert provenance["scope_team"] == "Inbound"
    assert provenance["scope_country"] == "EGY"
    assert provenance["performance_level"] == "Employee"
    assert provenance["operation_family"] == "read_employee_metric"
    assert provenance["evidence_revision"] == "synthetic-revision-7"
    assert provenance["prompt_version"] == "phase5-test-prompt-v1"
    assert len(provenance["prompt_sha256"]) == 64
    assert len(provenance["answer_snapshot_sha256"]) == 64
    assert len(provenance["evidence_snapshot_sha256"]) == 64
    serialized_provenance = json.dumps(provenance)
    assert "Nadia Fadel" not in serialized_provenance
    assert "6.2" not in serialized_provenance
    assert "client-invented-provider" not in serialized_provenance
    assert "client-invented-team" not in serialized_provenance
    assert len(governance["submission_idempotency"]) == 1

    conflict = client.post(
        "/api/ai/feedback",
        json={**payload, "rating": "up"},
        headers=headers,
    )
    assert conflict.status_code == 409, conflict.text

    try:
        FeedbackGovernanceService(db).record_workspace_or_pilot_feedback(
            payload=AiPilotFeedbackRequest(
                surface="workspace_chat",
                trace_id=str(row.id),
                rating="down",
                reason_tag="incorrect_answer",
                idempotency_key="different-owner-key",
            ),
            caller_user_id="manager-2",
            caller_role="Manager",
        )
    except TraceOwnershipError:
        pass
    else:
        raise AssertionError("A non-admin must not submit feedback for another user's trace")
    db.close()


def test_review_request_id_replays_without_duplicate_audit_and_conflicts_on_change():
    db = _make_session()
    row = _seed_trace(db)
    svc = FeedbackGovernanceService(db)

    first = svc.review_feedback(
        trace_id=str(row.id),
        reviewer_id="admin-reviewer-1",
        caller_role="Admin",
        decision="approved",
        notes="Verified against the synthetic source record.",
        request_id="review-request-001",
    )
    replay = svc.review_feedback(
        trace_id=str(row.id),
        reviewer_id="admin-reviewer-1",
        caller_role="Admin",
        decision="approved",
        notes="Verified against the synthetic source record.",
        request_id="review-request-001",
    )

    assert first is not None and replay is not None
    assert replay.model_dump(mode="json") == first.model_dump(mode="json")
    assert db.query(AuditLog).filter(AuditLog.operation == "AI_FEEDBACK_REVIEW").count() == 1
    db.refresh(row)
    assert row.reviewer_verified is True
    assert row.reviewer_id == "admin-reviewer-1"

    try:
        svc.review_feedback(
            trace_id=str(row.id),
            reviewer_id="admin-reviewer-1",
            caller_role="Admin",
            decision="rejected",
            request_id="review-request-001",
        )
    except FeedbackIdempotencyConflictError:
        pass
    else:
        raise AssertionError("Reusing a review request ID with a changed decision must conflict")
    assert db.query(AuditLog).filter(AuditLog.operation == "AI_FEEDBACK_REVIEW").count() == 1
    db.close()
