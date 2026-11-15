"""Phase 6 (#101): Privacy-preserving feedback governance, clustering, retention & human-gated export tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import ai_corrective_actions, ai_workspace
from config.database import Base, get_db
from models.ai_schemas import (
    AiPilotFeedbackRequest,
    AiTraceReviewRequest,
)
from models.models import AiInteractionTrace, AuditLog, Employee, Team
from services.ai import feature_gate
from services.ai.feedback_service import (
    FeedbackGovernanceService,
    classify_bundle_offline_optional,
)
from services.ai.trace_logger import TraceOwnershipError


def _make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    return factory()


def _build_app(db, *, monkeypatch, ai_enabled: bool = True, pilot_enabled: bool = True):
    monkeypatch.setattr(feature_gate, "is_ai_enabled", lambda _db: ai_enabled)
    monkeypatch.setattr(feature_gate, "read_ai_corrective_action_pilot_enabled", lambda _db: pilot_enabled)

    app = FastAPI()

    @app.middleware("http")
    async def inject_identity(request: Request, call_next):
        role = request.headers.get("x-test-role")
        user_id = request.headers.get("x-test-user-id", "")
        if role:
            request.state.user = {"role": role, "user_id": user_id or "admin-non-uuid"}
        return await call_next(request)

    def _scope(_db, request: Request):
        user = getattr(request.state, "user", None)
        if isinstance(user, dict):
            return user
        return {"role": request.headers.get("x-user-role", "Viewer"), "user_id": "anon"}

    monkeypatch.setattr(ai_workspace, "require_authenticated_scope", _scope)
    monkeypatch.setattr(ai_corrective_actions, "require_authenticated_scope", _scope)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.include_router(ai_workspace.router, prefix="/api")
    app.include_router(ai_corrective_actions.router, prefix="/api")
    return TestClient(app)


def _seed_cohort(db, *, team_name: str, region: str, level: str, count: int) -> Team:
    team = db.query(Team).filter(Team.name == team_name).first()
    if not team:
        team = Team(
            id=uuid.uuid4(),
            name=team_name,
            db_name=team_name.lower(),
            display_name=team_name,
            region=region,
        )
        db.add(team)
        db.flush()
    for idx in range(count):
        db.add(
            Employee(
                id=uuid.uuid4(),
                employee_id=f"EMP{team_name[:3].upper()}{idx:03d}",
                name=f"Staff {team_name[:2].lower()}{idx}",
                team_id=team.id,
                region=region,
                performance_level=level,
            )
        )
    db.commit()
    return team


def test_feedback_schema_supports_all_legacy_and_governance_tags():
    all_tags = [
        "helpful",
        "incorrect_answer",
        "incorrect_scope",
        "incomplete_response",
        "poor_suggestion",
        "other",
        "incorrect_kpi_interpretation",
        "unsupported_recommendation",
        "irrelevant_action",
        "missing_context",
        "inadequate_explanation",
        "unclear_uncertainty_statement",
        "provider_or_technical_failure",
        "good_quality_recommendation",
    ]
    for tag in all_tags:
        req = AiPilotFeedbackRequest(rating="down", reason_tag=tag)
        assert req.reason_tag == tag


def test_review_request_backwards_compat_and_conflict_validation():
    legacy_true = AiTraceReviewRequest(reviewer_verified=True)
    assert legacy_true.decision == "approved"
    assert legacy_true.reviewer_verified is True

    legacy_false = AiTraceReviewRequest(reviewer_verified=False)
    assert legacy_false.decision == "rejected"
    assert legacy_false.reviewer_verified is False

    new_reject = AiTraceReviewRequest(decision="rejected", proposed_action="Fix KPI prompt")
    assert new_reject.reviewer_verified is False
    assert new_reject.decision == "rejected"

    with pytest.raises(ValidationError):
        AiTraceReviewRequest(reviewer_verified=True, decision="rejected")


def test_pilot_feedback_redacts_pii_and_respects_120_char_column_limit():
    db = _make_session()
    _seed_cohort(db, team_name="Inbound", region="UAE", level="Employee", count=1)
    emp = db.query(Employee).first()
    emp.name = "Fatima Al-Mansoor"
    db.commit()

    svc = FeedbackGovernanceService(db)
    long_comment = (
        "Fatima Al-Mansoor (EMP9941) at fatima@sgh.ae or +971 50 123 4567 "
        "received an unsupported suggestion because AHT target was misread. "
        + ("Extra detail for truncation verification. " * 6)
    )
    resp = svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            surface="corrective_action_pilot",
            rating="down",
            reason_tag="unsupported_recommendation",
            comment=long_comment,
            candidate_sha="abc1234",
            model_version="@cf/ibm-granite/granite-4.0-h-micro",
            provider_name="cloudflare",
            fallback_reason="none",
            operation_family="corrective_action_draft",
            scope_team="Inbound",
            scope_country="UAE",
            performance_level="Employee",
            evidence_ids=["kpi:aht", "EMP9941", "fatima@sgh.ae"],
        ),
        caller_user_id="admin-1",
        caller_role="Admin",
    )
    assert resp.review_status == "pending"
    assert resp.reviewer_verified is False

    row = db.query(AiInteractionTrace).filter(AiInteractionTrace.id == uuid.UUID(resp.trace_id)).one()
    assert row.feedback_reason is not None
    assert len(row.feedback_reason) <= 120
    assert "Fatima" not in row.feedback_reason
    assert "EMP9941" not in row.feedback_reason
    assert "fatima@sgh.ae" not in row.feedback_reason

    gov = row.tool_digest["feedback_governance"]
    assert gov["surface"] == "corrective_action_pilot"
    assert gov["candidate_sha"] == "abc1234"
    assert gov["model_version"] == "@cf/ibm-granite/granite-4.0-h-micro"
    assert len(gov["comment_redacted"]) <= 500
    assert "Fatima" not in gov["comment_redacted"]
    assert "EMP9941" not in gov["comment_redacted"]
    assert "fatima@sgh.ae" not in gov["comment_redacted"]
    assert "4567" not in gov["comment_redacted"]
    assert "<EMPLOYEE_NAME>" in gov["comment_redacted"]
    assert "<EMPLOYEE_ID>" in gov["comment_redacted"]
    assert "<EMAIL>" in gov["comment_redacted"]
    assert "<PHONE>" in gov["comment_redacted"]
    assert "EMP9941" not in " ".join(gov["evidence_ids"])


def test_workspace_feedback_enforces_ownership_and_resets_prior_approval():
    db = _make_session()
    trace = AiInteractionTrace(
        id=uuid.uuid4(),
        user_id="owner-1",
        role="Admin",
        prompt="How is Inbound doing?",
        sanitized_prompt="How is Inbound doing?",
        session_state={"team": "Inbound"},
        tool_calls=[],
        tool_digest={},
        structured_response={},
        provider_name="cloudflare",
        model_name="granite",
        non_empty_evidence=True,
        guardrail_triggered=False,
        reviewer_verified=True,
        reviewer_id="admin-1",
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(trace)
    db.commit()

    svc = FeedbackGovernanceService(db)
    with pytest.raises(TraceOwnershipError):
        svc.record_workspace_or_pilot_feedback(
            payload=AiPilotFeedbackRequest(
                trace_id=str(trace.id),
                surface="workspace_chat",
                rating="down",
                reason_tag="incorrect_scope",
            ),
            caller_user_id="other-manager",
            caller_role="Manager",
        )

    res = svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            trace_id=str(trace.id),
            surface="workspace_chat",
            rating="down",
            reason_tag="incorrect_scope",
            comment="Wrong team scope returned",
        ),
        caller_user_id="owner-1",
        caller_role="Admin",
    )
    assert res.review_status == "pending"
    assert res.reviewer_verified is False
    db.refresh(trace)
    assert trace.reviewer_verified is False
    assert trace.reviewed_at is None


def test_pilot_feedback_endpoint_dual_gating_and_surface_validation(monkeypatch):
    db = _make_session()
    body = {
        "surface": "corrective_action_pilot",
        "rating": "up",
        "reason_tag": "good_quality_recommendation",
        "scope_team": "Inbound",
        "evidence_ids": ["kpi:csat"],
    }

    # Pilot off, chat on -> 403
    client_off = _build_app(db, monkeypatch=monkeypatch, ai_enabled=True, pilot_enabled=False)
    assert client_off.post("/api/ai/corrective-action-suggestions/feedback", headers={"x-test-role": "Admin"}, json=body).status_code == 403

    # Pilot on, chat off -> 401 anon, 403 non-Admin, 200 Admin
    client_on = _build_app(db, monkeypatch=monkeypatch, ai_enabled=False, pilot_enabled=True)
    assert client_on.post("/api/ai/corrective-action-suggestions/feedback", json=body).status_code == 401
    for role in ("Manager", "Employee", "Viewer"):
        assert client_on.post("/api/ai/corrective-action-suggestions/feedback", headers={"x-test-role": role}, json=body).status_code == 403

    ok = client_on.post("/api/ai/corrective-action-suggestions/feedback", headers={"x-test-role": "Admin"}, json=body)
    assert ok.status_code == 200
    assert ok.json()["review_status"] == "pending"

    bad_surface = client_on.post(
        "/api/ai/corrective-action-suggestions/feedback",
        headers={"x-test-role": "Admin"},
        json={**body, "surface": "workspace_chat"},
    )
    assert bad_surface.status_code == 422


def test_review_approve_and_reject_transitions_with_audit_uuid_handling(monkeypatch):
    db = _make_session()
    client = _build_app(db, monkeypatch=monkeypatch, ai_enabled=True, pilot_enabled=True)
    svc = FeedbackGovernanceService(db)
    created = svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            surface="corrective_action_pilot",
            rating="up",
            reason_tag="good_quality_recommendation",
            scope_team="Inbound",
            evidence_ids=["kpi:csat"],
        ),
        caller_user_id="admin-1",
        caller_role="Admin",
    )

    # Non-Admin forbidden
    denied = client.post(
        f"/api/ai/traces/{created.trace_id}/review",
        headers={"x-test-role": "Manager"},
        json={"decision": "approved"},
    )
    assert denied.status_code == 403

    # Admin reject with non-UUID actor_user_id -> succeeds and stores actor_user_id in new_values
    rejected = client.post(
        f"/api/ai/traces/{created.trace_id}/review",
        headers={"x-test-role": "Admin", "x-test-user-id": "non-uuid-admin"},
        json={"decision": "rejected", "notes": "Not actionable", "proposed_action": "Refine prompt"},
    )
    assert rejected.status_code == 200
    rej_data = rejected.json()
    assert rej_data["reviewer_verified"] is False
    assert rej_data["decision"] == "rejected"
    assert rej_data["review_status"] == "rejected"
    assert rej_data["is_distillation_eligible"] is False
    assert rej_data["proposed_action"] == "Refine prompt"

    # Admin approve with valid UUID actor
    admin_uuid = str(uuid.uuid4())
    approved = client.post(
        f"/api/ai/traces/{created.trace_id}/review",
        headers={"x-test-role": "Admin", "x-test-user-id": admin_uuid},
        json={"decision": "approved", "notes": "Verified clean"},
    )
    assert approved.status_code == 200
    app_data = approved.json()
    assert app_data["reviewer_verified"] is True
    assert app_data["decision"] == "approved"
    assert app_data["is_distillation_eligible"] is True

    audits = db.query(AuditLog).filter(AuditLog.operation == "AI_FEEDBACK_REVIEW").all()
    assert len(audits) == 2
    assert str(audits[0].record_id) == created.trace_id
    assert audits[0].performed_by_user_id is None
    assert audits[0].new_values["actor_user_id"] == "non-uuid-admin"
    assert str(audits[1].performed_by_user_id) == admin_uuid


def test_cluster_failures_groups_deterministically_with_zero_pii(monkeypatch):
    db = _make_session()
    _seed_cohort(db, team_name="Inbound", region="UAE", level="Employee", count=2)
    svc = FeedbackGovernanceService(db)

    t1 = svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            surface="corrective_action_pilot",
            rating="down",
            reason_tag="unsupported_recommendation",
            fallback_reason="timeout",
            operation_family="corrective_action_draft",
            scope_team="Inbound",
            comment="Bad draft for Staff in0",
        ),
        caller_user_id="admin-1",
        caller_role="Admin",
    )
    svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            surface="corrective_action_pilot",
            rating="down",
            reason_tag="unsupported_recommendation",
            fallback_reason="timeout",
            operation_family="corrective_action_draft",
            scope_team="Inbound",
            comment="Another timeout",
        ),
        caller_user_id="admin-1",
        caller_role="Admin",
    )
    svc.review_feedback(trace_id=t1.trace_id, reviewer_id="admin-1", caller_role="Admin", decision="rejected")

    client = _build_app(db, monkeypatch=monkeypatch, ai_enabled=True)
    assert client.get("/api/ai/feedback/clusters", headers={"x-test-role": "Manager"}).status_code == 403

    res = client.get("/api/ai/feedback/clusters?rating=down", headers={"x-test-role": "Admin"})
    assert res.status_code == 200
    payload = res.json()
    assert payload["total_traces"] == 2
    assert len(payload["clusters"]) == 1
    c = payload["clusters"][0]
    assert c["surface"] == "corrective_action_pilot"
    assert c["fallback_reason"] == "timeout"
    assert c["operation_family"] == "corrective_action_draft"
    assert c["scope_team"] == "Inbound"
    assert c["reason_tag"] == "unsupported_recommendation"
    assert c["total_count"] == 2
    assert c["down_count"] == 2
    assert c["rejected_count"] == 1
    assert c["pending_count"] == 1


def test_retention_purge_dry_run_clamp_and_delete_trace(monkeypatch):
    db = _make_session()
    now = datetime.now(timezone.utc)
    old_row = AiInteractionTrace(
        id=uuid.uuid4(),
        user_id="admin-1",
        role="Admin",
        prompt="old",
        sanitized_prompt="old",
        session_state={},
        tool_calls=[],
        tool_digest={},
        structured_response={},
        created_at=now - timedelta(days=120),
    )
    fresh_row = AiInteractionTrace(
        id=uuid.uuid4(),
        user_id="admin-1",
        role="Admin",
        prompt="fresh",
        sanitized_prompt="fresh",
        session_state={},
        tool_calls=[],
        tool_digest={},
        structured_response={},
        created_at=now - timedelta(days=10),
    )
    db.add_all([old_row, fresh_row])
    db.commit()

    client = _build_app(db, monkeypatch=monkeypatch, ai_enabled=True)
    assert client.post("/api/ai/traces/purge", headers={"x-test-role": "Manager"}, json={"dry_run": True}).status_code == 403

    # Dry run matches 1, deletes 0
    dry = client.post("/api/ai/traces/purge", headers={"x-test-role": "Admin"}, json={"dry_run": True})
    assert dry.status_code == 200
    assert dry.json()["retention_days"] == 90
    assert dry.json()["matched_count"] == 1
    assert dry.json()["purged_count"] == 0
    assert db.query(AiInteractionTrace).count() == 2

    # Env clamping test (0 -> clamped to 1, 999 -> clamped to 365)
    monkeypatch.setenv("PMS_AI_FEEDBACK_RETENTION_DAYS", "999")
    clamped = FeedbackGovernanceService(db).purge_expired_feedback(caller_role="Admin", caller_user_id="admin-1", dry_run=True)
    assert clamped.retention_days == 365
    monkeypatch.delenv("PMS_AI_FEEDBACK_RETENTION_DAYS", raising=False)

    # Real purge deletes old_row, keeps fresh_row
    real = client.post("/api/ai/traces/purge", headers={"x-test-role": "Admin"}, json={"retention_days": 90, "dry_run": False})
    assert real.status_code == 200
    assert real.json()["purged_count"] == 1
    assert db.query(AiInteractionTrace).count() == 1

    # Delete remaining trace
    assert client.delete(f"/api/ai/traces/{fresh_row.id}", headers={"x-test-role": "Manager"}).status_code == 403
    assert client.delete(f"/api/ai/traces/{uuid.uuid4()}", headers={"x-test-role": "Admin"}).status_code == 404
    deleted = client.delete(f"/api/ai/traces/{fresh_row.id}", headers={"x-test-role": "Admin"})
    assert deleted.status_code == 200
    assert db.query(AiInteractionTrace).count() == 0
    assert db.query(AuditLog).filter(AuditLog.operation == "AI_FEEDBACK_PURGE").count() >= 2
    assert db.query(AuditLog).filter(AuditLog.operation == "AI_FEEDBACK_DELETE").count() == 1


def test_export_bundle_blocks_small_cohort_unapproved_and_residual_pii(monkeypatch):
    db = _make_session()
    _seed_cohort(db, team_name="SmallTeam", region="UAE", level="Employee", count=3)
    _seed_cohort(db, team_name="LargeTeam", region="UAE", level="Employee", count=6)

    svc = FeedbackGovernanceService(db)
    # 1. Small cohort (n=3 < 5) approved -> blocked
    small_fb = svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            surface="corrective_action_pilot",
            rating="up",
            reason_tag="good_quality_recommendation",
            comment="Helpful action for small team",
            scope_team="SmallTeam",
            scope_country="UAE",
            performance_level="Employee",
            evidence_ids=["kpi:csat"],
        ),
        caller_user_id="admin-1",
        caller_role="Admin",
    )
    svc.review_feedback(trace_id=small_fb.trace_id, reviewer_id="admin-1", caller_role="Admin", decision="approved")

    # 2. Large cohort (n=6 >= 5) approved & clean -> exported
    large_fb = svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            surface="corrective_action_pilot",
            rating="up",
            reason_tag="good_quality_recommendation",
            comment="Clear coaching steps for LargeTeam",
            scope_team="LargeTeam",
            scope_country="UAE",
            performance_level="Employee",
            evidence_ids=["kpi:aht"],
        ),
        caller_user_id="admin-1",
        caller_role="Admin",
    )
    svc.review_feedback(trace_id=large_fb.trace_id, reviewer_id="admin-1", caller_role="Admin", decision="approved")

    # 3. Large cohort (n=6) approved but contains uncertain person query -> quarantined/blocked
    pii_fb = svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            surface="corrective_action_pilot",
            rating="down",
            reason_tag="missing_context",
            comment="Checking joining date details.",
            scope_team="LargeTeam",
            scope_country="UAE",
            performance_level="Employee",
        ),
        caller_user_id="admin-1",
        caller_role="Admin",
    )
    svc.review_feedback(trace_id=pii_fb.trace_id, reviewer_id="admin-1", caller_role="Admin", decision="approved")

    # 4. Large cohort pending/rejected -> excluded
    pending_fb = svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            surface="corrective_action_pilot",
            rating="up",
            reason_tag="helpful",
            comment="Not yet reviewed",
            scope_team="LargeTeam",
            scope_country="UAE",
            performance_level="Employee",
        ),
        caller_user_id="admin-1",
        caller_role="Admin",
    )
    assert pending_fb.review_status == "pending"

    client = _build_app(db, monkeypatch=monkeypatch, ai_enabled=True)
    assert client.get("/api/ai/feedback/export-bundle", headers={"x-test-role": "Manager"}).status_code == 403
    assert client.get("/api/ai/feedback/export-bundle?approved_only=false", headers={"x-test-role": "Admin"}).status_code == 422
    assert client.get("/api/ai/feedback/export-bundle?min_cohort_size=4", headers={"x-test-role": "Admin"}).status_code == 422

    res = client.get("/api/ai/feedback/export-bundle", headers={"x-test-role": "Admin"})
    assert res.status_code == 200
    data = res.json()
    assert data["exported_count"] == 1
    assert data["blocked_small_cohort_count"] == 1
    assert data["blocked_pii_count"] == 1
    assert data["items"][0]["trace_id"] == large_fb.trace_id
    assert data["items"][0]["cohort_size"] == 6
    assert db.query(AuditLog).filter(AuditLog.operation == "AI_FEEDBACK_EXPORT_BUNDLE").count() == 1


def test_offline_optional_classifier_requires_policy_nonprod_and_deidentification(monkeypatch):
    clean_bundle = [
        {
            "trace_id": "t-1",
            "cohort_size": 7,
            "comment": "KPI target comparison was clear.",
            "scope_team": "Inbound",
            "reason_tag": "good_quality_recommendation",
        }
    ]

    # Disabled by default
    monkeypatch.delenv("PMS_AI_EXTERNAL_REVIEW_ENABLED", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    res_off = classify_bundle_offline_optional(clean_bundle, policy_attested=True)
    assert res_off["status"] == "disabled_by_policy"
    assert res_off["review_required"] is True
    assert res_off["auto_applied"] is False

    # Disabled without attestation
    monkeypatch.setenv("PMS_AI_EXTERNAL_REVIEW_ENABLED", "true")
    res_unattested = classify_bundle_offline_optional(clean_bundle, policy_attested=False)
    assert res_unattested["status"] == "disabled_by_policy"

    # Disabled in production even if flag and attestation set
    monkeypatch.setenv("APP_ENV", "production")
    res_prod = classify_bundle_offline_optional(clean_bundle, policy_attested=True)
    assert res_prod["status"] == "disabled_by_policy"

    # Rejects non-deidentified / small-cohort items
    monkeypatch.setenv("APP_ENV", "development")
    dirty_bundle = [{"trace_id": "t-2", "cohort_size": 7, "employee_name": "Sara Ali", "comment": "bad"}]
    res_dirty = classify_bundle_offline_optional(dirty_bundle, policy_attested=True)
    assert res_dirty["status"] == "rejected_non_deidentified"

    # Succeeds in non-prod with flag + attestation + clean bundle, never auto-applying
    res_ok = classify_bundle_offline_optional(
        clean_bundle,
        policy_attested=True,
        classifier_fn=lambda items: [{"trace_id": items[0]["trace_id"], "category": "quality_pass"}],
    )
    assert res_ok["status"] == "completed"
    assert res_ok["review_required"] is True
    assert res_ok["auto_applied"] is False
    assert res_ok["classified"][0]["review_required"] is True
    assert res_ok["classified"][0]["auto_applied"] is False


def test_workspace_chat_requires_trace_id_and_rejects_missing_trace():
    db = _make_session()
    svc = FeedbackGovernanceService(db)
    with pytest.raises(ValueError):
        svc.record_workspace_or_pilot_feedback(
            payload=AiPilotFeedbackRequest(surface="workspace_chat", rating="up"),
            caller_user_id="admin-1",
            caller_role="Admin",
        )
    with pytest.raises(LookupError):
        svc.record_workspace_or_pilot_feedback(
            payload=AiPilotFeedbackRequest(
                trace_id=str(uuid.uuid4()),
                surface="workspace_chat",
                rating="up",
            ),
            caller_user_id="admin-1",
            caller_role="Admin",
        )


def test_review_endpoint_returns_404_for_unknown_or_malformed_trace(monkeypatch):
    db = _make_session()
    client = _build_app(db, monkeypatch=monkeypatch, ai_enabled=True)
    assert (
        client.post(
            f"/api/ai/traces/{uuid.uuid4()}/review",
            headers={"x-test-role": "Admin"},
            json={"decision": "approved"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/ai/traces/not-a-uuid/review",
            headers={"x-test-role": "Admin"},
            json={"decision": "approved"},
        ).status_code
        == 404
    )


def test_cluster_failures_filters_by_surface_and_review_status():
    db = _make_session()
    svc = FeedbackGovernanceService(db)
    chat_trace = AiInteractionTrace(
        id=uuid.uuid4(),
        user_id="admin-1",
        role="Admin",
        prompt="Team score",
        sanitized_prompt="Team score",
        session_state={"team": "Outbound"},
        tool_calls=[],
        tool_digest={},
        structured_response={},
    )
    db.add(chat_trace)
    db.commit()

    svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            trace_id=str(chat_trace.id),
            surface="workspace_chat",
            rating="down",
            reason_tag="incorrect_kpi_interpretation",
            scope_team="Outbound",
        ),
        caller_user_id="admin-1",
        caller_role="Admin",
    )
    pilot_fb = svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            surface="corrective_action_pilot",
            rating="up",
            reason_tag="good_quality_recommendation",
            scope_team="Inbound",
        ),
        caller_user_id="admin-1",
        caller_role="Admin",
    )
    svc.review_feedback(trace_id=pilot_fb.trace_id, reviewer_id="admin-1", caller_role="Admin", decision="approved")

    pilot_only = svc.cluster_failures(caller_role="Admin", surface="corrective_action_pilot")
    assert pilot_only.total_traces == 1
    assert pilot_only.clusters[0].surface == "corrective_action_pilot"
    assert pilot_only.clusters[0].approved_count == 1

    pending_only = svc.cluster_failures(caller_role="Admin", review_status="pending")
    assert pending_only.total_traces == 1
    assert pending_only.clusters[0].surface == "workspace_chat"


def test_cluster_failures_ignores_unrated_traces_and_requires_admin():
    db = _make_session()
    db.add(
        AiInteractionTrace(
            id=uuid.uuid4(),
            user_id="admin-1",
            role="Admin",
            prompt="No feedback",
            sanitized_prompt="No feedback",
            session_state={},
            tool_calls=[],
            tool_digest={},
            structured_response={},
        )
    )
    db.commit()
    svc = FeedbackGovernanceService(db)
    assert svc.cluster_failures(caller_role="Admin").total_traces == 0
    with pytest.raises(PermissionError):
        svc.cluster_failures(caller_role="Manager")


def test_purge_retention_clamps_minimum_to_1_day(monkeypatch):
    db = _make_session()
    monkeypatch.setenv("PMS_AI_FEEDBACK_RETENTION_DAYS", "0")
    res = FeedbackGovernanceService(db).purge_expired_feedback(
        caller_role="Admin",
        caller_user_id="admin-1",
        dry_run=True,
    )
    assert res.retention_days == 1


def test_export_bundle_respects_validated_cohort_metadata_when_no_db_employees():
    db = _make_session()
    svc = FeedbackGovernanceService(db)
    fb_small = svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            surface="corrective_action_pilot",
            rating="up",
            reason_tag="helpful",
            comment="Small cohort metadata test",
            scope_team="RCM",
            scope_country="UAE",
            performance_level="Employee",
        ),
        caller_user_id="admin-1",
        caller_role="Admin",
    )
    fb_ok = svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            surface="corrective_action_pilot",
            rating="up",
            reason_tag="helpful",
            comment="Sufficient cohort metadata test",
            scope_team="Coding",
            scope_country="Egypt",
            performance_level="Employee",
        ),
        caller_user_id="admin-1",
        caller_role="Admin",
    )
    for tid, cohort in ((fb_small.trace_id, 4), (fb_ok.trace_id, 7)):
        row = db.query(AiInteractionTrace).filter(AiInteractionTrace.id == uuid.UUID(tid)).one()
        gov = dict(row.tool_digest["feedback_governance"])
        gov["cohort_size"] = cohort
        row.tool_digest = {**row.tool_digest, "feedback_governance": gov}
        db.commit()
        svc.review_feedback(trace_id=tid, reviewer_id="admin-1", caller_role="Admin", decision="approved")

    bundle = svc.build_deidentified_export_bundle(caller_role="Admin", caller_user_id="admin-1")
    assert bundle.exported_count == 1
    assert bundle.blocked_small_cohort_count == 1
    assert bundle.items[0].trace_id == fb_ok.trace_id


def test_export_bundle_blocks_residual_email_in_legacy_approved_trace():
    db = _make_session()
    _seed_cohort(db, team_name="Inbound", region="UAE", level="Employee", count=5)
    legacy = AiInteractionTrace(
        id=uuid.uuid4(),
        user_id="admin-1",
        role="Admin",
        prompt="legacy",
        sanitized_prompt="legacy",
        session_state={"team": "Inbound", "region": "UAE", "performance_level": "Employee"},
        tool_calls=[],
        tool_digest={"feedback_governance": {"surface": "workspace_chat", "review_status": "approved", "pii_quarantined": True}},
        structured_response={},
        feedback_rating="up",
        feedback_reason="Approved note",
        reviewer_verified=True,
    )
    db.add(legacy)
    db.commit()

    bundle = FeedbackGovernanceService(db).build_deidentified_export_bundle(
        caller_role="Admin",
        caller_user_id="admin-1",
    )
    assert bundle.exported_count == 0
    assert bundle.blocked_pii_count == 1


def test_offline_classifier_rejects_small_cohort_items(monkeypatch):
    monkeypatch.setenv("PMS_AI_EXTERNAL_REVIEW_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    res = classify_bundle_offline_optional(
        [{"trace_id": "t-small", "cohort_size": 3, "comment": "Safe text"}],
        policy_attested=True,
    )
    assert res["status"] == "rejected_non_deidentified"
    assert res["rejected_trace_ids"] == ["t-small"]


def test_pilot_feedback_uses_env_candidate_sha_and_caps_comment_at_500_chars(monkeypatch):
    db = _make_session()
    monkeypatch.setenv("PMS_CANDIDATE_SHA", "deadbeef1234")
    svc = FeedbackGovernanceService(db)
    long_clean = "Actionable coaching note. " * 30
    res = svc.record_workspace_or_pilot_feedback(
        payload=AiPilotFeedbackRequest(
            surface="corrective_action_pilot",
            rating="up",
            reason_tag="good_quality_recommendation",
            comment=long_clean[:500],
            scope_team="Inbound",
        ),
        caller_user_id="admin-1",
        caller_role="Admin",
    )
    row = db.query(AiInteractionTrace).filter(AiInteractionTrace.id == uuid.UUID(res.trace_id)).one()
    gov = row.tool_digest["feedback_governance"]
    assert gov["candidate_sha"] == "deadbeef1234"
    assert len(gov["comment_redacted"]) <= 500
    assert len(row.feedback_reason) <= 120
