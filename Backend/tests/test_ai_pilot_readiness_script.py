"""Phase 9 (#103): Pilot readiness rehearsal script & release gate tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from services.ai import feature_gate

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
SCRIPT_PATH = REPO / "scripts" / "verify_ai_pilot_readiness.py"
REHEARSAL_REPORT_PATH = REPO / "evaluation" / "pms-ai" / "phase9" / "readiness_rehearsal_report.json"
CHECKLIST_PATH = REPO / "docs" / "ops" / "pms-ai-pilot-release-checklist.md"
SELF_HOSTED_DOC_PATH = REPO / "docs" / "ops" / "self-hosted-llm.md"
STATUS_DOC_PATH = REPO / "pms-ai" / "STATUS.md"


def _load_readiness_module():
    spec = importlib.util.spec_from_file_location("verify_ai_pilot_readiness_mod", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _use_real_feature_gate(monkeypatch):
    # Backend/conftest.py forces feature_gate.is_ai_enabled=True for legacy chat suites;
    # readiness gate verification requires the production read_ai_enabled behavior.
    monkeypatch.setattr(feature_gate, "is_ai_enabled", feature_gate.read_ai_enabled)


def test_readiness_script_exists_and_exposes_cli():
    mod = _load_readiness_module()
    args_default = mod._parse_args([])
    assert args_default.base_url is None
    assert args_default.json_out is None

    args_custom = mod._parse_args(["--in-process", "--json-out", "tmp/out.json", "--candidate-sha", "abc123"])
    assert args_custom.in_process is True
    assert args_custom.json_out == "tmp/out.json"
    assert args_custom.candidate_sha == "abc123"


def test_in_process_readiness_passes_all_technical_gates_and_keeps_human_gates_pending():
    mod = _load_readiness_module()
    report = mod.run_readiness_check(candidate_sha="0123456789abcdef")

    assert report["schema_version"] == "pms-ai-phase9-readiness-v1"
    assert report["mode"] == "in-process"
    assert report["read_only"] is True
    assert report["candidate_sha"] == "0123456789abcdef"
    assert report["technical_gates_passed"] is True
    assert report["pilot_ready_for_rollout"] is False
    assert report["secret_findings"] == []

    checks = report["checks"]
    assert checks["flags_default_off"]["passed"] is True
    assert checks["flags_default_off"]["ai_enabled"] is False
    assert checks["flags_default_off"]["ai_corrective_action_pilot_enabled"] is False
    assert checks["rbac_isolation"]["passed"] is True
    assert checks["diagnostics_truthfulness_and_secret_scan"]["passed"] is True
    assert checks["bounded_concurrency_and_timeout_fallback"]["passed"] is True
    assert checks["bounded_concurrency_and_timeout_fallback"]["concurrent_live_verify_status"] == 429


def test_readiness_latency_memory_and_blocking_human_gates_schema():
    mod = _load_readiness_module()
    report = mod.run_readiness_check()

    latency = report["latency_ms"]
    assert latency["samples"] >= 10
    assert latency["p50_ms"] is not None and latency["p50_ms"] >= 0.0
    assert latency["p95_ms"] is not None and latency["p95_ms"] >= latency["p50_ms"]
    assert latency["max_ms"] is not None and latency["max_ms"] >= latency["p95_ms"]

    mem = report["memory"]
    assert mem["peak_tracemalloc_mb"] is not None and mem["peak_tracemalloc_mb"] > 0.0

    gates = {g["gate_id"]: g for g in report["blocking_human_gates"]}
    assert gates["issue_97"]["ref"] == "#97"
    assert gates["issue_97"]["status"] == "PENDING"
    assert gates["vi_phase9_approval"]["owner"] == "Vi"
    assert gates["vi_phase9_approval"]["status"] == "PENDING"


def test_readiness_cli_json_out_writes_valid_report(tmp_path):
    mod = _load_readiness_module()
    out_file = tmp_path / "readiness.json"
    exit_code = mod.main(["--in-process", "--json-out", str(out_file), "--candidate-sha", "cafebabe"])
    assert exit_code == 0
    written = json.loads(out_file.read_text(encoding="utf-8"))
    assert written["candidate_sha"] == "cafebabe"
    assert written["technical_gates_passed"] is True
    assert written["pilot_ready_for_rollout"] is False


def test_secret_scanner_detects_known_secret_shapes():
    mod = _load_readiness_module()
    assert mod._scan_secrets({"host": "api.cloudflare.com", "ok": True}) == []
    found = mod._scan_secrets(
        {
            "a": "sk-1234567890abcdef123456",
            "b": "AIzaSyDummyKeyValue1234567890abcd",
            "c": "Bearer mySecretBearerToken12345",
            "d": "postgresql://admin:supersecret@db.internal:5432/pms",
        }
    )
    assert set(found) == {"openai_key", "google_api_key", "bearer_token", "postgres_credentials"}


def test_percentile_helper_handles_empty_and_ordered_values():
    mod = _load_readiness_module()
    assert mod._percentile([], 50) is None
    assert mod._percentile([5.0, 1.0, 3.0, 2.0, 4.0], 50) == 3.0
    assert mod._percentile([5.0, 1.0, 3.0, 2.0, 4.0], 95) == 5.0


def test_readiness_in_process_does_not_mutate_default_flags_in_fresh_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        assert feature_gate.read_ai_enabled(db) is False
        assert feature_gate.read_ai_corrective_action_pilot_enabled(db) is False
    finally:
        db.close()
        engine.dispose()


def test_remote_read_only_mode_blocks_when_admin_bearer_missing():
    mod = _load_readiness_module()

    def fake_probe(url, *, method="GET", headers=None, json_body=None, timeout=5.0):
        assert method == "GET"
        return 401, {"detail": "Authentication required"}, 1.5

    with patch.object(mod, "_http_read_probe", side_effect=fake_probe):
        with patch.dict("os.environ", {"PMS_READINESS_ADMIN_BEARER": "", "PMS_READINESS_NON_ADMIN_BEARER": ""}):
            report = mod.run_readiness_check(base_url="https://pms.example.internal")

    assert report["mode"] == "remote-read-only"
    assert report["read_only"] is True
    assert report["checks"]["rbac_isolation"]["passed"] is True
    assert report["checks"]["flags_default_off"]["status"] == "blocked_missing_admin_bearer"
    assert report["technical_gates_passed"] is False


def test_remote_read_only_mode_passes_with_mocked_admin_and_non_admin_tokens():
    mod = _load_readiness_module()

    def fake_probe(url, *, method="GET", headers=None, json_body=None, timeout=5.0):
        assert method == "GET"
        auth = (headers or {}).get("Authorization", "")
        if auth == "Bearer admin-tok":
            if url.endswith("/api/settings/ai-assistant"):
                return 200, {"data": {"enabled": False, "corrective_action_pilot_enabled": False}}, 2.0
            if url.endswith("/api/ai/diagnostics"):
                return 200, {"data": {"feature_enabled": False, "pilot_role_restricted": True}}, 3.0
        if auth == "Bearer viewer-tok":
            return 403, {"detail": "Admin required"}, 1.5
        return 401, {"detail": "Authentication required"}, 1.2

    with patch.object(mod, "_http_read_probe", side_effect=fake_probe):
        with patch.dict(
            "os.environ",
            {
                "PMS_READINESS_ADMIN_BEARER": "admin-tok",
                "PMS_READINESS_NON_ADMIN_BEARER": "viewer-tok",
            },
        ):
            report = mod.run_readiness_check(base_url="https://pms.example.internal")

    assert report["technical_gates_passed"] is True
    assert report["pilot_ready_for_rollout"] is False
    assert report["secret_findings"] == []


def test_remote_read_only_mode_fails_if_flag_is_enabled():
    mod = _load_readiness_module()

    def fake_probe(url, *, method="GET", headers=None, json_body=None, timeout=5.0):
        auth = (headers or {}).get("Authorization", "")
        if auth == "Bearer admin-tok":
            if url.endswith("/api/settings/ai-assistant"):
                return 200, {"data": {"enabled": False, "corrective_action_pilot_enabled": True}}, 2.0
            if url.endswith("/api/ai/diagnostics"):
                return 200, {"data": {"feature_enabled": False}}, 2.0
        return 401, {}, 1.0

    with patch.object(mod, "_http_read_probe", side_effect=fake_probe):
        with patch.dict("os.environ", {"PMS_READINESS_ADMIN_BEARER": "admin-tok"}):
            report = mod.run_readiness_check(base_url="https://pms.example.internal")

    assert report["checks"]["flags_default_off"]["passed"] is False
    assert report["technical_gates_passed"] is False


def test_committed_rehearsal_report_is_valid_and_secret_free():
    assert REHEARSAL_REPORT_PATH.exists()
    report = json.loads(REHEARSAL_REPORT_PATH.read_text(encoding="utf-8"))
    mod = _load_readiness_module()

    assert report["schema_version"] == "pms-ai-phase9-readiness-v1"
    assert report["technical_gates_passed"] is True
    assert report["pilot_ready_for_rollout"] is False
    assert mod._scan_secrets(report) == []
    assert any(g["ref"] == "#97" and g["status"] == "PENDING" for g in report["blocking_human_gates"])
    assert any(g["owner"] == "Vi" and g["status"] == "PENDING" for g in report["blocking_human_gates"])


def test_release_checklist_and_ops_docs_cover_kill_switch_rollback_and_pending_gates():
    checklist = CHECKLIST_PATH.read_text(encoding="utf-8")
    assert "/api/settings/ai-corrective-action-pilot" in checklist
    assert "/api/settings/ai-assistant" in checklist
    assert "Dokploy" in checklist
    assert "#97" in checklist
    assert "Vi" in checklist
    assert "PENDING" in checklist
    assert "Stage 1" in checklist and "Stage 4" in checklist
    assert "ai_enabled" in checklist

    self_hosted = SELF_HOSTED_DOC_PATH.read_text(encoding="utf-8")
    assert "UnifiedProviderEngine" in self_hosted
    assert "pms-ai-pilot-release-checklist.md" in self_hosted

    status_doc = STATUS_DOC_PATH.read_text(encoding="utf-8")
    assert "Phase 9" in status_doc
    assert "Vi" in status_doc


def test_in_process_checks_produce_zero_database_writes():
    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from models.models import Action, AuditLog, ProductSetting

    mod = _load_readiness_module()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        before_settings = db.query(func.count(ProductSetting.key)).scalar()
        before_audits = db.query(func.count(AuditLog.id)).scalar()
        before_actions = db.query(func.count(Action.id)).scalar()
        report = mod.run_readiness_check()
        assert report["technical_gates_passed"] is True
        assert db.query(func.count(ProductSetting.key)).scalar() == before_settings
        assert db.query(func.count(AuditLog.id)).scalar() == before_audits
        assert db.query(func.count(Action.id)).scalar() == before_actions
    finally:
        db.close()
        engine.dispose()
