"""Phase 1: Admin diagnostics, truthful catalog evidence, and AI rollback."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import ai_workspace
from config.database import Base, get_db
from models.ai_schemas import AiCatalogMetricItem, AiCatalogEvidence, AiChatRequest, SessionFilterContext
from models.models import Employee, PerformanceRecord, Team, UploadLog
from services.ai import feature_gate
from services.ai.catalog import evidence_for_team, get_ai_catalog
from services.ai.coverage_manifest import build_coverage_manifest, validate_coverage_manifest
from services.ai.evidence import CatalogEvidence, evidence_passes, publish_evidence
from services.ai.llm_client import probe_model_availability
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.runtime_status import last_fallback, note_fallback, reset_runtime_status
from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records

API_KEY = "phase1-test-key-should-not-leak"
PASSWORD = "phase1pass-should-not-leak"
PROMPT = "SECRET_PROMPT_TEXT_should_not_appear"
HIDDEN_NAME = "Hidden Person Qx9zz"


def _flags_off(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "PMS_AI_LLM_INTENT_ENABLED",
        "PMS_AI_LLM_SYNTHESIS_ENABLED",
        "PMS_AI_LLM_EXPLORATION_ENABLED",
        "PMS_AI_LOCAL_ROUTER_ENABLED",
        "PMS_AI_LOCAL_SYNTHESIS_ENABLED",
        "PMS_AI_LOCAL_EXPLORATION_ENABLED",
        "PMS_AI_LOCAL_DATA_EXPLORATION_ENABLED",
    ):
        monkeypatch.setenv(name, "false")


def _app(monkeypatch: pytest.MonkeyPatch, session_factory):
    monkeypatch.setattr(feature_gate, "is_ai_enabled", feature_gate.read_ai_enabled)
    app = FastAPI()

    @app.middleware("http")
    async def _state_user(request, call_next):
        role = request.headers.get("x-test-state-role")
        if role:
            request.state.user = {"role": role, "user_id": "user-1"}
        return await call_next(request)

    app.include_router(ai_workspace.router, prefix="/api")
    app.include_router(ai_workspace.diagnostics_router, prefix="/api")

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _memory_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_missing_evidence_never_counts_as_a_pass() -> None:
    pending = CatalogEvidence(
        state="verified",
        tests=("Backend/tests/test_ai_phase1_runtime.py",),
        fixture_or_source_version="pms-ai-english-eval-v1",
        reviewed_on="2026-11-10",
        reviewer="pending",
    )
    assert evidence_passes(pending) is False
    assert publish_evidence(pending) == ("blocked", False)

    undated = CatalogEvidence(
        state="verified_no_data",
        tests=("Backend/tests/test_ai_phase1_runtime.py",),
        fixture_or_source_version="source-v1",
        reviewed_on="",
        reviewer="A reviewer",
    )
    assert evidence_passes(undated) is False
    assert publish_evidence(undated)[1] is False

    partial = CatalogEvidence(
        state="partial",
        tests=("Backend/tests/test_ai_phase1_runtime.py",),
        fixture_or_source_version="source-v1",
        reviewed_on="2026-11-10",
        reviewer="A reviewer",
    )
    assert evidence_passes(partial) is False
    assert publish_evidence(partial) == ("partial", False)

    complete = CatalogEvidence(
        state="verified",
        tests=("Backend/tests/test_ai_phase1_runtime.py",),
        fixture_or_source_version="source-v1",
        reviewed_on="2026-11-10",
        reviewer="A reviewer",
    )
    assert evidence_passes(complete) is True
    assert publish_evidence(complete) == ("verified", True)

    coerced = AiCatalogMetricItem(
        metric_id="inbound:score",
        kpi_key="OverallScore",
        display_name="Score",
        team="Inbound",
        function="Call Center",
        status="verified",
        evidence=AiCatalogEvidence(reviewer="pending"),
        evidence_passes=True,
    )
    assert coerced.status == "blocked"
    assert coerced.evidence_passes is False


def test_live_catalog_has_no_default_certification() -> None:
    catalog = get_ai_catalog()
    rows = catalog.get_full_coverage_scope_registry()
    assert rows
    assert all(row["certified"] is False and row["passes"] is False for row in rows)
    assert all(row["evidence_state"] in {"partial", "blocked"} for row in rows)
    assert all(row["evidence"]["reviewer"] in {"", "pending"} for row in rows)
    assert not any(row["evidence"]["reviewed_on"] for row in rows)
    passing_metrics = [
        metric
        for metric in catalog.metrics.values()
        if metric.status in {"verified", "verified_no_data"} or evidence_passes(metric.evidence)
    ]
    assert passing_metrics == []
    inbound = evidence_for_team("Inbound")
    assert inbound.state == "partial"
    assert inbound.tests == ("Backend/tests/test_ai_workspace.py",)
    assert inbound.fixture_or_source_version == "pms-ai-english-eval-v1"
    assert evidence_for_team("Coding").state == "blocked"

    manifest = build_coverage_manifest()
    cells = manifest["coverage_cells"]
    assert cells
    assert all(cell["evidence_passes"] is False for cell in cells)
    assert all(cell["coverage_state"] not in {"verified", "verified_no_data", "CERTIFIED"} for cell in cells)
    report = validate_coverage_manifest(manifest)
    assert report["passed"] is True
    assert report["certified_total"] == 0


def test_diagnostics_auth_boundary_and_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_runtime_status()
    _flags_off(monkeypatch)
    monkeypatch.setenv("PMS_AI_LLM_API_KEY", API_KEY)
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", f"http://phase1user:{PASSWORD}@127.0.0.1:9/v1")
    monkeypatch.setattr(
        "services.ai.diagnostics.probe_model_availability",
        lambda timeout_seconds=0.8: {
            "available": False,
            "name": API_KEY,
            "version": f"http://phase1user:{PASSWORD}@127.0.0.1:9/v1",
            "probe": "not_sent",
            "reason": f"http://phase1user:{PASSWORD}@127.0.0.1:9/v1",
            "last_known": None,
        },
    )
    note_fallback(PROMPT, "routing")
    factory = _memory_factory()
    db = factory()
    team = Team(id=uuid.uuid4(), name="Inbound", db_name="Inbound", region="EGY", team_level="employee")
    db.add(team)
    db.flush()
    uploaded_at = datetime(2026, 11, 1, 8, 30, tzinfo=timezone.utc)
    db.add(
        UploadLog(
            id=uuid.uuid4(),
            team_id=team.id,
            month="September",
            year=2026,
            record_count=1,
            status="success",
            error_message=HIDDEN_NAME,
            uploaded_at=uploaded_at,
        )
    )
    employee = Employee(
        id=uuid.uuid4(),
        employee_id="HID-1",
        name=HIDDEN_NAME,
        team_id=team.id,
        region="EGY",
        performance_level="Employee",
    )
    db.add(employee)
    db.flush()
    db.add(
        PerformanceRecord(
            id=uuid.uuid4(),
            year=2026,
            employee_id=employee.id,
            team_id=team.id,
            month="September",
            performance_level="Employee",
            score=12.34,
            grade="D",
            status="Below",
            uploaded_at=uploaded_at,
        )
    )
    db.commit()
    db.close()

    client = _app(monkeypatch, factory)
    anonymous = client.get("/api/ai/diagnostics")
    assert anonymous.status_code == 401
    assert anonymous.json()["detail"] == "Authentication required"

    manager = client.get("/api/ai/diagnostics", headers={"X-User-Role": "Manager"})
    assert manager.status_code == 403
    assert manager.json()["detail"] == "PMS AI is limited to administrators during the pilot."

    spoofed = client.get(
        "/api/ai/diagnostics",
        headers={"X-User-Role": "Admin", "X-Test-State-Role": "Employee"},
    )
    assert spoofed.status_code == 403

    admin = client.get("/api/ai/diagnostics", headers={"X-User-Role": "Admin"})
    assert admin.status_code == 200
    body = admin.json()
    encoded = json.dumps(body)
    assert API_KEY not in encoded
    assert PASSWORD not in encoded
    assert PROMPT not in encoded
    assert HIDDEN_NAME not in encoded
    assert "12.34" not in encoded
    assert "base_url" not in encoded
    assert "api_key" not in encoded
    data = body["data"]
    assert data["feature"]["ai_enabled"] is False
    assert data["feature"]["intent_enabled"] is False
    assert data["feature"]["synthesis_enabled"] is False
    assert data["feature"]["exploration_enabled"] is False
    assert data["providers"] == {"routing": "deterministic", "synthesis": "deterministic"}
    assert data["model"]["available"] is False
    assert data["model"]["name"] == "[REDACTED]"
    assert PASSWORD not in data["model"]["reason"]
    assert data["last_fallback"]["reason"] == "unspecified"
    assert data["dataset"]["status"] == "ok"
    assert data["dataset"]["latest_upload_at"].startswith("2026-11-01T08:30:00")
    assert data["dataset"]["latest_performance_record_at"].startswith("2026-11-01T08:30:00")

    closed = client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json={"prompt": "Hi"})
    assert closed.status_code == 403
    assert closed.json()["detail"] == "PMS AI is turned off."
    catalog = client.get("/api/ai/catalog", headers={"X-User-Role": "Admin"})
    assert catalog.status_code == 403
    assert catalog.json()["detail"] == "PMS AI is turned off."


def test_model_probe_returns_before_a_slow_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://127.0.0.1:9")

    class _Slow:
        def open(self, *_args, **_kwargs):
            time.sleep(2)
            raise TimeoutError("slow")

    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_args, **_kwargs: _Slow())
    started = time.perf_counter()
    result = probe_model_availability(0.3)
    elapsed = time.perf_counter() - started
    assert elapsed < 1.5
    assert result["available"] is False
    assert result["reason"] == "timeout"
    assert "127.0.0.1" not in json.dumps(result)
    assert "http" not in json.dumps(result)


def test_turning_ai_off_and_model_flags_off_returns_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    _flags_off(monkeypatch)
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")

    def boom(*_args, **_kwargs):
        raise AssertionError("the model was called while routing flags are off")

    monkeypatch.setattr("services.ai.local_model_router.chat_completion", boom)
    monkeypatch.setattr("services.ai.local_evidence_synthesis.chat_completion", boom)
    monkeypatch.setattr("services.ai.local_data_explorer.chat_completion", boom)

    records = [_make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", 91.0, 45, 50, 90, 200)]
    _patch_records(monkeypatch, records)
    db = _build_in_memory_db()
    try:
        response = PmsAiOrchestrator(
            db,
            {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True},
        ).run_chat_turn(
            AiChatRequest(
                prompt="What is the Inbound team score in September 2026?",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            )
        )
    finally:
        db.close()
    assert response.outcome == "answer"
    assert response.headline
    assert response.provider_used != "llama_cpp"
    assert response.provider_usage.provider_calls == 0

    reset_runtime_status()
    monkeypatch.setenv("PMS_AI_LLM_INTENT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LLM_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LLM_EXPLORATION_ENABLED", "false")
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("PMS_AI_LLM_TIMEOUT_SECONDS", "0.4")
    monkeypatch.setenv("PMS_AI_LLM_SYNTHESIS_TIMEOUT_SECONDS", "0.4")
    monkeypatch.setattr("services.ai.local_model_router.chat_completion", __import__("services.ai.llm_client", fromlist=["chat_completion"]).chat_completion)
    monkeypatch.setattr("services.ai.local_evidence_synthesis.chat_completion", __import__("services.ai.llm_client", fromlist=["chat_completion"]).chat_completion)
    _patch_records(monkeypatch, records)
    db = _build_in_memory_db()
    try:
        fallback = PmsAiOrchestrator(
            db,
            {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True},
        ).run_chat_turn(
            AiChatRequest(
                prompt="What is the Inbound score?",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            )
        )
    finally:
        db.close()
    assert fallback.outcome == "answer"
    assert fallback.headline
    assert fallback.provider_used == "deterministic"
    assert fallback.provider_usage.fallback_outcome == "unavailable_or_invalid"
    assert last_fallback()["reason"] == "unavailable_or_invalid"
