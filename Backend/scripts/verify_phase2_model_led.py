r"""Phase 2 Verification: Model-Led Pilot vs Baseline Comparison.

Workspace: D:\Projects\PMS_Dashboard\Backend
Tests isolated local in-memory SQLite and synthetic records through authenticated chat API.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import calendar
from types import SimpleNamespace
from typing import Any

# Ensure Backend is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base, get_db
from config.environment import load_project_environment
from models.ai_schemas import (
    AiChatRequest,
    SessionFilterContext,
)
from models.schemas import (
    CallsData,
    EvaluationData,
    GeoBreakdown,
    GeoData,
    PerformanceRecord,
)
from services.ai.catalog import ai_evidence_cache
from services.ai.llm_client import (
    configured_providers,
    local_intent_enabled,
    local_synthesis_enabled,
)
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.provider_engine import load_unified_provider_config
from services.dashboard_record_service import DashboardRecordService
from services.database_record_source import DatabaseRecordSource

# Load environment configuration
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_project_environment(backend_dir)
os.environ["PMS_AI_PROVIDER_TIMEOUT_SECONDS"] = "15.0"

PROVIDER_METRIC_EVENTS: list[dict[str, Any]] = []
_PROVIDER_METRIC_LOG_RE = re.compile(
    r"UnifiedProviderEngine purpose=(?P<purpose>\S+) outcome=(?P<outcome>\S+) "
    r"provider=(?P<provider>\S+) model=(?P<model>\S+) latency_ms=(?P<latency>[\d.]+) "
    r"tokens=(?P<tokens>\d+) neurons=(?P<neurons>[\d.]+) cost=\$(?P<cost>[\d.]+) "
    r"fallback_used=(?P<fallback>True|False)"
)


class ProviderMetricCapture(logging.Handler):
    """Capture only aggregate provider usage fields; never prompt or response text."""

    def emit(self, record: logging.LogRecord) -> None:
        match = _PROVIDER_METRIC_LOG_RE.search(record.getMessage())
        if not match:
            return
        values = match.groupdict()
        PROVIDER_METRIC_EVENTS.append(
            {
                "purpose": values["purpose"],
                "outcome": values["outcome"],
                "provider": values["provider"],
                "model": values["model"],
                "latency_ms": float(values["latency"]),
                "tokens": int(values["tokens"]),
                "neurons": float(values["neurons"]),
                "estimated_cost_usd_from_provider_log": float(values["cost"]),
                "fallback_used": values["fallback"] == "True",
            }
        )


_provider_metric_capture = ProviderMetricCapture()


def _observed_provider_events(start_index: int) -> list[dict[str, Any]]:
    return [dict(event) for event in PROVIDER_METRIC_EVENTS[start_index:]]


def provider_configuration_snapshot() -> dict[str, Any]:
    """Record safe provider configuration metadata without emitting credentials."""
    cfg = load_unified_provider_config()
    return {
        "primary_provider_configured": cfg.effective_primary_provider,
        "primary_model_configured": (
            cfg.cloudflare_model if cfg.effective_primary_provider == "cloudflare" else cfg.nvidia_model
        ),
        "fallback_provider_configured": cfg.effective_fallback_provider,
        "fallback_model_configured": (
            cfg.nvidia_model if cfg.effective_fallback_provider == "nvidia" else cfg.cloudflare_model
        ),
        "fallback_enabled": bool(cfg.fallback_enabled),
        "configured_usable_provider_order": configured_providers(cfg),
        "credential_presence": {
            "cloudflare_account_id": bool(cfg.cloudflare_account_id),
            "cloudflare_api_token": bool(cfg.cloudflare_api_token),
            "nvidia_api_key": bool(cfg.nvidia_api_key),
        },
        "intent_enabled": local_intent_enabled(),
        "synthesis_enabled": local_synthesis_enabled(),
        "provider_timeout_seconds": cfg.timeout_seconds,
        "max_retries": cfg.max_retries,
    }


def _waiting_time_evidence(response: dict[str, Any], *, period: str, actual: float) -> dict[str, Any]:
    year, month = period.split("-", maxsplit=1)
    human_period = f"{calendar.month_name[int(month)]} {year}".casefold()
    matches = [
        item
        for item in response.get("typed_evidence", [])
        if str(item.get("kpi_key") or "").casefold().replace("_", "") == "waitingtime"
        and str(item.get("period") or "").casefold() in {period.casefold(), human_period}
        and item.get("actual") is not None
        and abs(float(item["actual"]) - actual) < 0.01
    ]
    assert matches, f"Missing Waiting Time evidence for {period}={actual}: {response.get('typed_evidence')}"
    evidence = matches[0]
    assert evidence.get("unit") == "min", f"Waiting Time unit must be min: {evidence}"
    assert evidence.get("target") is not None and abs(float(evidence["target"]) - 5.0) < 0.01, evidence
    assert str(evidence.get("direction") or "").casefold() == "lower_better", evidence
    return evidence


def _assert_waiting_time_missed_target(
    response: dict[str, Any], *, period: str, actual: float, gap: float
) -> None:
    _waiting_time_evidence(response, period=period, actual=actual)
    text = " ".join(
        [str(response.get("headline") or ""), *[str(x) for x in response.get("narrative_bullets", [])]]
    ).casefold()
    assert any(
        marker in text
        for marker in (
            "did not meet",
            "not meeting",
            "not met",
            "missed the target",
            "exceeded the target",
            "exceeding the target",
            "above the target",
            "over the target",
        )
    ), f"Expected an explicit lower-is-better target miss: {text}"
    # A correct denial may contain “not meeting the target”; remove those forms
    # before rejecting positive target claims.
    positive_check = text
    for negative in ("did not meet the target", "not meeting the target", "not met the target"):
        positive_check = positive_check.replace(negative, "")
    assert not any(
        marker in positive_check
        for marker in ("met the target", "meeting the target", "achieved the target", "within the target")
    ), f"Incorrect positive target status in response: {text}"
    assert "5.0" in text, f"Target value missing from response: {text}"
    assert f"{gap:.1f}" in text, f"Target miss gap {gap:.1f} missing from response: {text}"


def _usage_summary(response: dict[str, Any]) -> dict[str, Any]:
    usage = response.get("provider_usage") or {}
    return {
        "provider_calls": int(usage.get("provider_calls") or 0),
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "estimated_cost_usd": float(usage.get("estimated_cost_usd") or 0.0),
        "fallback_outcome": str(usage.get("fallback_outcome") or "none"),
    }


def _record_check(result: dict[str, Any], condition: bool, message: str) -> None:
    if not condition:
        result.setdefault("verification_failures", []).append(message)


def _make_synth_records() -> list[PerformanceRecord]:
    recs: list[PerformanceRecord] = []

    # Nadia Fadel in August 2026 (Waiting Time = 6.8 min)
    r_aug = PerformanceRecord(
        id="Inbound_EMP501_2026_Aug",
        employee_id="EMP501",
        employee_name="Nadia Fadel",
        team="Inbound",
        month="August",
        year=2026,
        region="EGY",
        position="Senior Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=88.5, grade="B"),
        calls=CallsData(inbound=450, total_handled=520, abandoned=10),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=110, sharjah=40, ajman=20, clinics=10),
            attended=GeoBreakdown(dubai=95, sharjah=35, ajman=18, clinics=8),
        ),
        kpi_values=[
            {
                "kpi_key": "waitingtime",
                "label": "Waiting Time",
                "actual_value": 6.8,
                "target_value": 5.0,
                "unit": "min",
                "direction": "lower_better",
            },
            {
                "kpi_key": "bookings_count",
                "label": "Bookings Count",
                "actual_value": 180,
                "target_value": 150,
                "unit": "count",
                "direction": "higher_better",
            },
            {
                "kpi_key": "overall_score",
                "label": "Overall Score",
                "actual_value": 88.5,
                "target_value": 85.0,
                "unit": "%",
                "direction": "higher_better",
            },
        ],
    )
    recs.append(r_aug)

    # Nadia Fadel in September 2026 (Waiting Time = 6.2 min)
    r_sep = PerformanceRecord(
        id="Inbound_EMP501_2026_Sep",
        employee_id="EMP501",
        employee_name="Nadia Fadel",
        team="Inbound",
        month="September",
        year=2026,
        region="EGY",
        position="Senior Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=91.0, grade="A"),
        calls=CallsData(inbound=480, total_handled=550, abandoned=8),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=130, sharjah=45, ajman=25, clinics=10),
            attended=GeoBreakdown(dubai=115, sharjah=40, ajman=22, clinics=9),
        ),
        kpi_values=[
            {
                "kpi_key": "waitingtime",
                "label": "Waiting Time",
                "actual_value": 6.2,
                "target_value": 5.0,
                "unit": "min",
                "direction": "lower_better",
            },
            {
                "kpi_key": "bookings_count",
                "label": "Bookings Count",
                "actual_value": 210,
                "target_value": 150,
                "unit": "count",
                "direction": "higher_better",
            },
            {
                "kpi_key": "overall_score",
                "label": "Overall Score",
                "actual_value": 91.0,
                "target_value": 85.0,
                "unit": "%",
                "direction": "higher_better",
            },
        ],
    )
    recs.append(r_sep)

    # Ambiguous Mariams in September 2026
    r_m1 = PerformanceRecord(
        id="Inbound_EMP601_2026_Sep",
        employee_id="EMP601",
        employee_name="Mariam Ali",
        team="Inbound",
        month="September",
        year=2026,
        region="EGY",
        position="Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=87.0, grade="B"),
        calls=CallsData(inbound=300, total_handled=350, abandoned=15),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=80, sharjah=30, ajman=10, clinics=5),
            attended=GeoBreakdown(dubai=70, sharjah=25, ajman=8, clinics=4),
        ),
        kpi_values=[
            {
                "kpi_key": "overall_score",
                "label": "Overall Score",
                "actual_value": 87.0,
                "target_value": 85.0,
                "unit": "%",
                "direction": "higher_better",
            }
        ],
    )
    r_m2 = PerformanceRecord(
        id="Inbound_EMP602_2026_Sep",
        employee_id="EMP602",
        employee_name="Mariam Hassan",
        team="Inbound",
        month="September",
        year=2026,
        region="EGY",
        position="Call Center Agent",
        performance_level="Employee",
        status="Below Target",
        evaluation=EvaluationData(score=79.0, grade="C"),
        calls=CallsData(inbound=280, total_handled=320, abandoned=20),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=70, sharjah=25, ajman=10, clinics=5),
            attended=GeoBreakdown(dubai=60, sharjah=20, ajman=8, clinics=4),
        ),
        kpi_values=[
            {
                "kpi_key": "overall_score",
                "label": "Overall Score",
                "actual_value": 79.0,
                "target_value": 85.0,
                "unit": "%",
                "direction": "higher_better",
            }
        ],
    )
    recs.extend([r_m1, r_m2])
    return recs


def _patch_data_sources(records: list[PerformanceRecord]):
    DatabaseRecordSource.get_all = lambda *args, **kwargs: records
    DashboardRecordService.list_analysis_records = lambda *args, **kwargs: records


def run_conversation_sequence(
    client: TestClient,
    admin_token: str,
    pilot_enabled: bool,
    label: str,
) -> list[dict[str, Any]]:
    results = []
    headers = {"Authorization": f"Bearer {admin_token}"}
    print(f"\n{'='*70}\nStarting Conversation Sequence via HTTP POST /api/ai/chat: {label} (Pilot Enabled={pilot_enabled})\n{'='*70}")

    # Turn 1: Nadia Fadel Waiting Time in September 2026
    t1_prompt = "What was Nadia Fadel's Waiting Time in September 2026?"
    t1_event_start = len(PROVIDER_METRIC_EVENTS)
    t1_http = client.post("/api/ai/chat", json={"prompt": t1_prompt}, headers=headers)
    assert t1_http.status_code == 200, f"Turn 1 HTTP failed: {t1_http.status_code} {t1_http.text}"
    t1_resp = t1_http.json()["data"]
    t1_data = {
        "turn": 1,
        "prompt": t1_prompt,
        "http_status": t1_http.status_code,
        "outcome": t1_resp["outcome"],
        "headline": t1_resp["headline"],
        "answer_source": t1_resp.get("answer_source", "deterministic"),
        "provider_used": t1_resp["provider_used"],
        "model_used": t1_resp["model_used"],
        "tool_calls": [tc["tool_name"] for tc in t1_resp.get("tool_calls", [])],
        "latency_ms": t1_resp["latency_ms"],
        **_usage_summary(t1_resp),
        "observed_provider_events": _observed_provider_events(t1_event_start),
        "observed_estimated_cost_usd": round(
            sum(event["estimated_cost_usd_from_provider_log"] for event in PROVIDER_METRIC_EVENTS[t1_event_start:]), 8
        ),
        "verification_failures": [],
        "primary_source_link": t1_resp.get("primary_source_link"),
        "conversation_id": t1_resp.get("conversation_id"),
    }
    results.append(t1_data)
    print(f"\n[Turn 1] Prompt: {t1_prompt}")
    print(f"Outcome: {t1_resp['outcome']}")
    print(f"Headline: {t1_resp['headline']}")
    print(f"Answer Source: {t1_data['answer_source']} | Provider: {t1_resp['provider_used']} | Model: {t1_resp['model_used']} | Latency: {t1_resp['latency_ms']}ms")
    print(f"Tools: {t1_data['tool_calls']} | Fallback: {t1_data['fallback_outcome']}")
    print(f"Source: {t1_resp.get('primary_source_link')}")
    if pilot_enabled:
        _record_check(t1_data, t1_data["answer_source"] == "model_synthesis", f"Expected model_synthesis, got {t1_data['answer_source']}")
        try:
            _assert_waiting_time_missed_target(t1_resp, period="2026-09", actual=6.2, gap=1.2)
        except AssertionError as exc:
            _record_check(t1_data, False, str(exc))

    # Turn 2: Follow-up "And in August?"
    t2_prompt = "And in August?"
    t2_event_start = len(PROVIDER_METRIC_EVENTS)
    t2_http = client.post(
        "/api/ai/chat",
        json={
            "prompt": t2_prompt,
            "conversation_id": t1_resp["conversation_id"],
            "context_version": t1_resp["context_version"],
            "session_state": t1_resp["resolved_session_state"],
        },
        headers=headers,
    )
    assert t2_http.status_code == 200, f"Turn 2 HTTP failed: {t2_http.status_code} {t2_http.text}"
    t2_resp = t2_http.json()["data"]
    t2_data = {
        "turn": 2,
        "prompt": t2_prompt,
        "http_status": t2_http.status_code,
        "outcome": t2_resp["outcome"],
        "headline": t2_resp["headline"],
        "answer_source": t2_resp.get("answer_source", "deterministic"),
        "provider_used": t2_resp["provider_used"],
        "model_used": t2_resp["model_used"],
        "tool_calls": [tc["tool_name"] for tc in t2_resp.get("tool_calls", [])],
        "latency_ms": t2_resp["latency_ms"],
        **_usage_summary(t2_resp),
        "observed_provider_events": _observed_provider_events(t2_event_start),
        "observed_estimated_cost_usd": round(
            sum(event["estimated_cost_usd_from_provider_log"] for event in PROVIDER_METRIC_EVENTS[t2_event_start:]), 8
        ),
        "verification_failures": [],
        "primary_source_link": t2_resp.get("primary_source_link"),
    }
    results.append(t2_data)
    print(f"\n[Turn 2] Prompt: {t2_prompt}")
    print(f"Outcome: {t2_resp['outcome']}")
    print(f"Headline: {t2_resp['headline']}")
    print(f"Answer Source: {t2_data['answer_source']} | Provider: {t2_resp['provider_used']} | Model: {t2_resp['model_used']} | Latency: {t2_resp['latency_ms']}ms")
    print(f"Tools: {t2_data['tool_calls']} | Fallback: {t2_data['fallback_outcome']}")
    print(f"Source: {t2_resp.get('primary_source_link')}")
    if pilot_enabled:
        _record_check(t2_data, t2_data["answer_source"] == "model_synthesis", f"Expected model_synthesis, got {t2_data['answer_source']}")
        try:
            _assert_waiting_time_missed_target(t2_resp, period="2026-08", actual=6.8, gap=1.8)
        except AssertionError as exc:
            _record_check(t2_data, False, str(exc))

    # Turn 3: Multi-month trend across available months
    t3_prompt = "How did her Waiting Time change across the available months?"
    t3_event_start = len(PROVIDER_METRIC_EVENTS)
    t3_http = client.post(
        "/api/ai/chat",
        json={
            "prompt": t3_prompt,
            "conversation_id": t1_resp["conversation_id"],
            "context_version": t2_resp["context_version"],
            "session_state": t2_resp["resolved_session_state"],
        },
        headers=headers,
    )
    assert t3_http.status_code == 200, f"Turn 3 HTTP failed: {t3_http.status_code} {t3_http.text}"
    t3_resp = t3_http.json()["data"]
    t3_data = {
        "turn": 3,
        "prompt": t3_prompt,
        "http_status": t3_http.status_code,
        "outcome": t3_resp["outcome"],
        "headline": t3_resp["headline"],
        "answer_source": t3_resp.get("answer_source", "deterministic"),
        "provider_used": t3_resp["provider_used"],
        "model_used": t3_resp["model_used"],
        "tool_calls": [tc["tool_name"] for tc in t3_resp.get("tool_calls", [])],
        "latency_ms": t3_resp["latency_ms"],
        **_usage_summary(t3_resp),
        "observed_provider_events": _observed_provider_events(t3_event_start),
        "observed_estimated_cost_usd": round(
            sum(event["estimated_cost_usd_from_provider_log"] for event in PROVIDER_METRIC_EVENTS[t3_event_start:]), 8
        ),
        "verification_failures": [],
        "primary_source_link": t3_resp.get("primary_source_link"),
    }
    results.append(t3_data)
    print(f"\n[Turn 3] Prompt: {t3_prompt}")
    print(f"Outcome: {t3_resp['outcome']}")
    print(f"Headline: {t3_resp['headline']}")
    print(f"Answer Source: {t3_data['answer_source']} | Provider: {t3_resp['provider_used']} | Model: {t3_resp['model_used']} | Latency: {t3_resp['latency_ms']}ms")
    print(f"Tools: {t3_data['tool_calls']} | Fallback: {t3_data['fallback_outcome']}")
    print(f"Source: {t3_resp.get('primary_source_link')}")
    if pilot_enabled:
        _record_check(t3_data, t3_data["answer_source"] == "model_synthesis", f"Expected model_synthesis, got {t3_data['answer_source']}")
        _record_check(
            t3_data,
            "6.8" in t3_resp["headline"] and "6.2" in t3_resp["headline"],
            f"Expected 6.8 and 6.2 in headline: {t3_resp['headline']}",
        )
        _record_check(t3_data, "0.6" in t3_resp["headline"], f"Expected 0.6 in headline: {t3_resp['headline']}")
        trend_text = (t3_resp["headline"] + " " + " ".join(t3_resp.get("narrative_bullets", []))).casefold()
        _record_check(t3_data, "improv" in trend_text, f"Lower Waiting Time should be described as an improvement: {trend_text}")
        _record_check(
            t3_data,
            not any(word in trend_text for word in ("worsened", "deteriorated")),
            f"Waiting Time trend has wrong direction: {trend_text}",
        )

    return results


def run_security_and_edge_cases(
    client: TestClient,
    admin_token: str,
    emp_token: str,
) -> dict[str, Any]:
    print(f"\n{'='*70}\nRunning Security & Edge Cases via HTTP POST /api/ai/chat (Pilot Enabled=True)\n{'='*70}")
    os.environ["PMS_AI_MODEL_LED_PILOT_ENABLED"] = "true"
    ai_evidence_cache.clear()

    # 1. Non-Admin user denial via HTTP endpoint
    emp_resp = client.post(
        "/api/ai/chat",
        json={"prompt": "What was Nadia Fadel's Waiting Time in September 2026?"},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    print(f"\n[Security Check 1: Non-Admin Role 'Employee' via HTTP]")
    print(f"HTTP Status: {emp_resp.status_code}")
    non_admin_denied = (emp_resp.status_code == 403) or (
        emp_resp.status_code == 200 and emp_resp.json().get("data", {}).get("outcome") == "restricted_access"
    )
    assert non_admin_denied, f"Expected non-admin access denial, got HTTP {emp_resp.status_code}: {emp_resp.text}"
    print("Non-Admin user access correctly denied via HTTP endpoint.")

    # 2. Ambiguous employee resolution via HTTP endpoint
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    ambig_http = client.post(
        "/api/ai/chat",
        json={"prompt": "What was Mariam's score?"},
        headers=admin_headers,
    )
    assert ambig_http.status_code == 200, f"Ambiguous query HTTP failed: {ambig_http.status_code}"
    ambig_resp = ambig_http.json()["data"]
    print(f"\n[Edge Case 2: Ambiguous Employee 'Mariam' via HTTP]")
    print(f"Outcome: {ambig_resp['outcome']}")
    print(f"Headline: {ambig_resp['headline']}")
    clar_choices = ambig_resp.get("clarification", {}).get("choices", []) if ambig_resp.get("clarification") else []
    print(f"Clarification Choices: {clar_choices}")
    assert ambig_resp["outcome"] == "clarification", f"Expected clarification, got {ambig_resp['outcome']}"
    assert ambig_resp.get("clarification") is not None and ambig_resp["clarification"].get("code") == "AMBIGUOUS_PERSON"
    print("Ambiguous employee correctly surfaced clarification choices via HTTP.")

    # 3. Disambiguation selection follow-up via HTTP endpoint
    selected_choice = ambig_resp["resolved_session_state"]["last_confirmed_query"]["pending_clarification_choices"][0]
    sel_http = client.post(
        "/api/ai/chat",
        json={
            "prompt": "Mariam Ali",
            "conversation_id": ambig_resp["conversation_id"],
            "context_version": ambig_resp["context_version"],
            "session_state": ambig_resp["resolved_session_state"],
            "clarification_choice_id": selected_choice["id"],
        },
        headers=admin_headers,
    )
    assert sel_http.status_code == 200, f"Selection query HTTP failed: {sel_http.status_code}"
    sel_resp = sel_http.json()["data"]
    print(f"\n[Edge Case 3: Selection of Candidate '{selected_choice['employee_name']}' via HTTP]")
    print(f"Outcome: {sel_resp['outcome']}")
    print(f"Headline: {sel_resp['headline']}")
    assert sel_resp["outcome"] == "answer"
    assert "Mariam Ali" in sel_resp["headline"] or "87" in sel_resp["headline"]
    print("Disambiguation selection correctly resolved candidate and preserved query via HTTP.")

    return {
        "non_admin_denied": non_admin_denied,
        "ambiguous_clarification": ambig_resp["outcome"] == "clarification",
        "selection_resolved": sel_resp["outcome"] == "answer",
    }


def main():
    PROVIDER_METRIC_EVENTS.clear()
    provider_logger = logging.getLogger("services.ai.provider_engine")
    provider_logger.addHandler(_provider_metric_capture)
    configured_provider_snapshot = provider_configuration_snapshot()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()

    records = _make_synth_records()
    _patch_data_sources(records)

    from app import app
    from services.auth_service import AuthenticationService

    admin_user = AuthenticationService.create_user(db, "admin_verifier", "admin@verify.local", "AdminVerifyPass123!", role="Admin")
    admin_token = AuthenticationService.authenticate_user(db, "admin_verifier", "AdminVerifyPass123!")

    emp_user = AuthenticationService.create_user(db, "emp_verifier", "emp@verify.local", "EmpVerifyPass123!", role="Employee")
    emp_token = AuthenticationService.authenticate_user(db, "emp_verifier", "EmpVerifyPass123!")

    fastapi_app = getattr(app, "other_asgi_app", app)
    fastapi_app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)

    # Enable AI Assistant switch via authorized Admin endpoint
    sw_resp = client.put(
        "/api/settings/ai-assistant",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert sw_resp.status_code == 200, f"Could not enable AI Assistant: {sw_resp.text}"

    # Run A: Baseline with Pilot Flag OFF
    os.environ["PMS_AI_MODEL_LED_PILOT_ENABLED"] = "false"
    ai_evidence_cache.clear()
    baseline_results = run_conversation_sequence(client, admin_token, pilot_enabled=False, label="Run A: Baseline (Pilot OFF)")

    # Run B: Pilot with Flag ON
    os.environ["PMS_AI_MODEL_LED_PILOT_ENABLED"] = "true"
    ai_evidence_cache.clear()
    pilot_results = run_conversation_sequence(client, admin_token, pilot_enabled=True, label="Run B: Model-Led Pilot (Pilot ON)")

    # Run C: Security and Edge Cases
    edge_results = run_security_and_edge_cases(client, admin_token, emp_token)

    actual_pilot_turns = pilot_results
    providers_observed = sorted({str(row.get("provider_used") or "unknown") for row in actual_pilot_turns})
    models_observed = sorted({str(row.get("model_used") or "unknown") for row in actual_pilot_turns})
    provider_calls = len(PROVIDER_METRIC_EVENTS)
    total_cost_usd = round(
        sum(event["estimated_cost_usd_from_provider_log"] for event in PROVIDER_METRIC_EVENTS), 8
    )
    provider_tokens = sum(int(event.get("tokens") or 0) for event in PROVIDER_METRIC_EVENTS)
    verification_failures = [
        {"turn": row.get("turn"), "failures": row.get("verification_failures", [])}
        for row in pilot_results
        if row.get("verification_failures")
    ]
    if not any(row.get("provider_used") in configured_provider_snapshot["configured_usable_provider_order"] for row in pilot_results):
        verification_failures.append(
            {"turn": None, "failures": ["No configured usable provider was observed in actual model-led runtime use."]}
        )

    # Keep provider configuration and observed runtime use in separate fields.
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "authentication": "authenticated Admin bearer token",
        "data_source": "synthetic in-memory SQLite fixtures",
        "configured_provider_snapshot": configured_provider_snapshot,
        "actual_runtime_use": {
            "providers_observed": providers_observed,
            "models_observed": models_observed,
            "provider_calls": provider_calls,
            "tokens_observed_from_provider_logs": provider_tokens,
            "estimated_cost_usd": total_cost_usd,
            "fallback_outcomes": sorted({str(row.get("fallback_outcome") or "none") for row in actual_pilot_turns}),
            "answer_sources": sorted({str(row.get("answer_source") or "unknown") for row in actual_pilot_turns}),
            "provider_call_events": [dict(event) for event in PROVIDER_METRIC_EVENTS],
        },
        "baseline_run": baseline_results,
        "pilot_run": pilot_results,
        "security_and_edge_cases": edge_results,
        "verification_failures": verification_failures,
    }
    report_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "phase2_model_led_http_trace_20261117.json",
    )
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    provider_logger.removeHandler(_provider_metric_capture)
    print(f"\nVerification completed! Summary saved to {report_path}")
    print(f"Configured provider order: {configured_provider_snapshot['configured_usable_provider_order']}")
    print(f"Observed runtime providers/models: {providers_observed} / {models_observed}")
    print(f"Provider calls: {provider_calls} | Tokens observed: {provider_tokens} | Estimated cost USD: {total_cost_usd:.8f}")
    if verification_failures:
        print(f"Verification failures: {verification_failures}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
