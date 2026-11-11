"""Phase 1 delta on top of the #84 diagnostics and evidence registry."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import ai_workspace
from config.database import get_db
from models.ai_schemas import AiChatRequest, SessionFilterContext
from services.ai import feature_gate
from services.ai.catalog import CatalogMetricDefinition, get_ai_catalog
from services.ai.coverage_manifest import build_coverage_manifest
from services.ai.evidence import CatalogEvidence, evidence_passes, publish_evidence
from services.ai.llm_client import check_model_health
from services.ai.orchestrator import PmsAiOrchestrator
from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records

MODEL_ID = "qwen3-4b-q4_k_m"


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


_PASSING_STATES = {"verified", "verified_no_data", "certified", "CERTIFIED"}
_PENDING_REVIEWERS = {"", "pending", "unknown", "none", "n/a", "na", "tbd", "unreviewed"}


def _evidence_is_complete(evidence: dict) -> bool:
    tests = [str(item).strip() for item in (evidence.get("tests") or []) if str(item).strip()]
    reviewer = str(evidence.get("reviewer") or "").strip().casefold()
    return bool(tests) and bool(str(evidence.get("fixture_or_source_version") or "").strip()) and bool(
        str(evidence.get("reviewed_on") or "").strip()
    ) and reviewer not in _PENDING_REVIEWERS


def test_verified_or_certified_requires_evidence_and_a_reviewer() -> None:
    """A verified or certified label without linked evidence and a real reviewer is a failure."""
    incomplete = CatalogEvidence(
        state="verified",
        tests=("Backend/tests/test_ai_phase1_runtime.py",),
        fixture_or_source_version="pms-ai-english-eval-v1",
        reviewed_on="2026-11-10",
        reviewer="pending",
    )
    assert evidence_passes(incomplete) is False
    assert publish_evidence(incomplete) == ("blocked", False)
    assert publish_evidence(CatalogEvidence(state="verified", reviewer="")) == ("blocked", False)
    complete = CatalogEvidence(
        state="verified",
        tests=("Backend/tests/test_ai_phase1_runtime.py",),
        fixture_or_source_version="pms-ai-english-eval-v1",
        reviewed_on="2026-11-10",
        reviewer="Vi",
    )
    assert evidence_passes(complete) is True
    assert publish_evidence(complete) == ("verified", True)

    assert CatalogMetricDefinition.__dataclass_fields__["status"].default == "blocked"
    catalog = get_ai_catalog()
    for metric in catalog.metrics.values():
        if metric.status in _PASSING_STATES or evidence_passes(metric.evidence):
            published = {
                "tests": list(metric.evidence.tests),
                "fixture_or_source_version": metric.evidence.fixture_or_source_version,
                "reviewed_on": metric.evidence.reviewed_on,
                "reviewer": metric.evidence.reviewer,
            }
            assert _evidence_is_complete(published), metric.metric_id
            assert evidence_passes(metric.evidence) is True
    assert not any(metric.status in _PASSING_STATES for metric in catalog.metrics.values())

    for row in catalog.get_full_coverage_scope_registry():
        if row.get("certified") or row.get("passes") or row.get("evidence_state") in _PASSING_STATES or row.get("status") in _PASSING_STATES:
            assert _evidence_is_complete(row.get("evidence") or {}), row["team"]
    assert not any(row.get("certified") or row.get("evidence_state") in _PASSING_STATES for row in catalog.get_full_coverage_scope_registry())

    cells = build_coverage_manifest()["coverage_cells"]
    assert cells
    for cell in cells:
        state = str(cell.get("coverage_state") or "")
        if state in _PASSING_STATES or cell.get("evidence_passes") is True:
            assert _evidence_is_complete(cell.get("evidence") or {}), cell.get("team")
    assert not any(str(cell.get("coverage_state")) in _PASSING_STATES for cell in cells)


def test_shared_all_region_finance_and_rcm_are_not_certified() -> None:
    rows = {row["team"]: row for row in get_ai_catalog().get_full_coverage_scope_registry()}
    assert rows["Finance"]["region"] == "All"
    assert rows["RCM"]["region"] == "All"
    assert rows["Finance"]["certified"] is False
    assert rows["RCM"]["certified"] is False
    assert rows["Finance"]["evidence"]["reviewer"] == "pending"
    assert rows["RCM"]["evidence"]["reviewer"] == "pending"


def test_diagnostics_stay_open_for_an_admin_when_ai_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(feature_gate, "is_ai_enabled", lambda db: False)
    app = FastAPI()
    app.include_router(ai_workspace.router, prefix="/api")
    app.include_router(ai_workspace.diagnostics_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: None
    client = TestClient(app)

    anonymous = client.get("/api/ai/diagnostics")
    assert anonymous.status_code == 401

    manager = client.get("/api/ai/diagnostics", headers={"X-User-Role": "Manager"})
    assert manager.status_code == 403
    assert manager.json()["detail"] == "PMS AI is limited to administrators during the pilot."

    admin = client.get("/api/ai/diagnostics", headers={"X-User-Role": "Admin"})
    assert admin.status_code == 200
    data = admin.json()["data"]
    assert data["feature_enabled"] is False
    assert data["routing_provider"] == "deterministic"
    assert data["synthesis_provider"] == "deterministic"
    assert "model_version" in data
    assert "api_key" not in json.dumps(admin.json()).casefold()

    chat = client.post("/api/ai/chat", headers={"X-User-Role": "Admin"}, json={"prompt": "Hi"})
    assert chat.status_code == 403
    assert chat.json()["detail"] == "PMS AI is turned off."


def test_real_model_probe_reads_version_and_does_not_hang(monkeypatch: pytest.MonkeyPatch) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path != "/v1/models":
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps({"data": [{"id": MODEL_ID}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            body = json.dumps(
                {"model": MODEL_ID, "choices": [{"message": {"role": "assistant", "content": "ready"}}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("PMS_AI_LLM_BASE_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setenv("PMS_AI_LLM_MODEL", MODEL_ID)
        started = time.perf_counter()
        health = check_model_health(1.5)
        assert time.perf_counter() - started < 2.5
        assert health["available"] is True
        assert health["inference_verified"] is True
        assert health["model_version"] == MODEL_ID
        assert "api_key" not in json.dumps(health).casefold()
        assert f"127.0.0.1:{port}" not in json.dumps(health)
    finally:
        server.shutdown()
        server.server_close()

    class _Slow:
        def open(self, *_args, **_kwargs):
            time.sleep(1.5)
            raise TimeoutError("slow")

    monkeypatch.setattr("services.ai.llm_client.urllib.request.build_opener", lambda *_a, **_k: _Slow())
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://127.0.0.1:9")
    started = time.perf_counter()
    hung = check_model_health(0.3)
    assert time.perf_counter() - started < 1.0
    assert hung["available"] is False
    assert hung["reason"] == "timeout"
    assert hung["model_version"] is None
    time.sleep(1.6)


def test_crashing_model_probe_is_reported_as_probe_error_not_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A probe that raises is a probe bug, not a slow model: report probe_error."""

    def _boom(*_args, **_kwargs):
        raise RuntimeError("probe blew up")

    monkeypatch.setattr("services.ai.llm_client._probe_configured_model", _boom)
    started = time.perf_counter()
    health = check_model_health(1.5)
    assert time.perf_counter() - started < 1.0
    assert health["available"] is False
    assert health["inference_verified"] is False
    assert health["reason"] == "probe_error"
    assert health["model_version"] is None


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

    from services.ai.llm_client import chat_completion

    monkeypatch.setenv("PMS_AI_LLM_INTENT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LLM_SYNTHESIS_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("PMS_AI_LLM_TIMEOUT_SECONDS", "0.4")
    monkeypatch.setenv("PMS_AI_LLM_SYNTHESIS_TIMEOUT_SECONDS", "0.4")
    monkeypatch.setattr("services.ai.local_model_router.chat_completion", chat_completion)
    monkeypatch.setattr("services.ai.local_evidence_synthesis.chat_completion", chat_completion)
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
    # Since #92, a refused model connection is named specifically instead of
    # collapsing to the generic bucket: the endpoint at 127.0.0.1:9 refuses
    # the connection, so the fallback outcome is "connection_refused".
    assert fallback.provider_usage.fallback_outcome == "connection_refused"
