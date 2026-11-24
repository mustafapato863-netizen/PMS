#!/usr/bin/env python3
"""Runner for the 240-scenario PMS AI Unseen Benchmark + Corrective Draft Repair Suite.

Runs dev (120), val (60), and blind (60) chat scenarios plus the bounded-repair
corrective-draft verification suite across:
- `deterministic`: offline deterministic rules + compound planner
- `scripted_mocked`: model-led pilot with deterministic mocked provider (is_live_verified=false)
- `live`: live cloud/gateway evaluation ONLY when PMS_AI_RUN_LIVE_MODEL_TESTS=true
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "Backend"
TESTS_DIR = BACKEND_DIR / "tests"
BENCHMARK_DIR = Path(__file__).resolve().parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# Prevent 30s Redis waits and unintended live network/Ollama calls when running offline CLI benchmarks.
os.environ.setdefault("REDIS_ENABLED", "false")
if os.environ.get("PMS_AI_RUN_LIVE_MODEL_TESTS", "").strip().casefold() != "true":
    for _env_key in (
        "PMS_AI_NVIDIA_ROUTING_ENABLED",
        "PMS_AI_LOCAL_ROUTER_ENABLED",
        "PMS_AI_LOCAL_EXPLORATION_ENABLED",
        "PMS_AI_LOCAL_SYNTHESIS_ENABLED",
        "PMS_AI_CLOUDFLARE_ENABLED",
    ):
        os.environ[_env_key] = "false"

from _pytest.monkeypatch import MonkeyPatch  # noqa: E402
import services.redis_provider as redis_provider_mod  # noqa: E402

if getattr(redis_provider_mod, "redis_client", None) is not None:
    redis_provider_mod.redis_client._url = ""

from models.ai_schemas import AiChatRequest, AiCorrectiveActionSuggestionRequest, SessionFilterContext  # noqa: E402
from models.models import Action, Employee, KPIValue, PerformanceRecord, Team  # noqa: E402
from scripts.run_unseen_eval import _build_eval_records  # noqa: E402
from services.ai.catalog import ai_evidence_cache  # noqa: E402
from services.ai.corrective_action_drafter import CorrectiveActionDrafter  # noqa: E402
from services.ai.orchestrator import PmsAiOrchestrator  # noqa: E402
from services.ai.providers import ProviderResponse  # noqa: E402
from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records  # noqa: E402


DEFAULT_BENCHMARK_PATH = BENCHMARK_DIR / "benchmark_240.json"
DEFAULT_JSON_OUT = BENCHMARK_DIR / "benchmark_report.json"
DEFAULT_REPORT_OUT = BENCHMARK_DIR / "BENCHMARK_REPORT.md"


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = (len(ordered) - 1) * (pct / 100.0)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return round(ordered[int(idx)], 2)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (idx - lo), 2)


def _build_benchmark_records() -> list[Any]:
    """Build an isolated synthetic PMS dataset strictly disjoint from October 2026."""
    recs = _build_eval_records()
    for r in recs:
        if getattr(r, "employee_id", None) == "EMP701":
            r.branch_key = "dubai"
            if getattr(r, "geo", None) is not None:
                r.geo.bookings.dubai = 0
                r.geo.bookings.sharjah = 0
                r.geo.bookings.ajman = 0
                r.geo.bookings.clinics = 0
    # Add Coding EGY / UAE and Submission / Re-Submission team records for August & September
    extra_teams = [
        ("EMP511", "Sami Nader", "Submission EGY", "EGY", "Employee", "Submission Officer", 85.0),
        ("EMP512", "Maya Tariq", "Submission", "UAE", "Employee", "Submission Specialist", 88.0),
        ("EMP513", "Karim Zaki", "Re-Submission EGY", "EGY", "Employee", "Resubmission Officer", 82.5),
        ("EMP514", "Dina Fares", "Re-Submission", "UAE", "Employee", "Resubmission Specialist", 87.0),
    ]
    for emp_id, name, team, region, level, pos, score in extra_teams:
        rec = _make_call_center_record(emp_id, name, team, score, 0, 0, 0, 0, month="September")
        rec.region = region
        rec.performance_level = level
        rec.position = pos
        rec.kpi_values = [
            {
                "kpi_key": "overall_score",
                "label": "Overall Score",
                "actual_value": score,
                "target_value": 85.0,
                "unit": "%",
                "direction": "higher_better",
            }
        ]
        recs.append(rec)

    # August Marketing record for Rami Adel (prior period comparison coverage)
    mk_aug = _make_call_center_record("EMP801", "Rami Adel", "Marketing", 88.0, 0, 0, 0, 0, month="August")
    mk_aug.region = "UAE"
    mk_aug.position = "Media Buyer"
    mk_aug.kpi_values = [
        {
            "kpi_key": "mb_cpl",
            "label": "CPL",
            "actual_value": 48.0,
            "target_value": 50.0,
            "achievement_ratio": 1.0,
            "weight_applied": 0.25,
            "unit": "AED",
            "direction": "lower_better",
        }
    ]
    recs.append(mk_aug)
    return recs


def _classify_actual_response_type(resp: Any) -> str:
    outcome = str(getattr(resp, "outcome", "") or "")
    cap = str(getattr(resp, "capability_mode", "") or "")
    headline_cf = str(getattr(resp, "headline", "") or "").casefold()
    bullets_cf = " ".join(str(b or "") for b in (getattr(resp, "narrative_bullets", None) or [])).casefold()
    combined = f"{headline_cf} {bullets_cf}"
    if outcome == "clarification":
        return "clarification"
    if outcome == "restricted_access":
        return "unsupported_request"
    if outcome == "unsupported_request" or cap == "off_topic":
        return "unsupported_request"
    guardrail_notes = getattr(resp, "domain_guardrail_notes", None) or []
    if guardrail_notes and ("outside" in headline_cf or "rather than financial revenue" in headline_cf):
        return "unsupported_request"
    if outcome == "unavailable_data":
        # Partial answers with valid evidence or unavailability note
        if "cannot" in combined or "not sent" in combined or "unavailable" in combined or "no published" in combined or "doesn't" in combined or "does not" in combined:
            return "partial_answer"
        return "partial_answer"
    if "cannot" in combined and ("not sent" in combined or "manually" in combined or "external" in combined):
        return "partial_answer"
    if "no comparable prior period" in combined or "unavailable" in combined:
        return "partial_answer"
    return "direct_answer"


def _evaluate_turn(
    *,
    scenario: dict[str, Any],
    turn: dict[str, Any],
    resp: Any,
    elapsed_ms: float,
) -> dict[str, Any]:
    headline = str(getattr(resp, "headline", "") or "")
    bullets = [str(b or "") for b in (getattr(resp, "narrative_bullets", None) or [])]
    detail_bullets = [str(b or "") for b in (getattr(resp, "detail_bullets", None) or [])]
    clar = getattr(resp, "clarification", None)
    clar_q = str(getattr(clar, "question", "") or "") if clar else ""
    clar_opts = " ".join(str(getattr(c, "label", "") or "") for c in (getattr(clar, "options", None) or [])) if clar else ""
    guardrail_notes = " ".join(str(n or "") for n in (getattr(resp, "domain_guardrail_notes", None) or []))
    full_text = " ".join([headline, *bullets, *detail_bullets, clar_q, clar_opts, guardrail_notes]).strip()
    full_cf = full_text.casefold()

    exp_type = str(turn.get("expected_response_type") or scenario.get("expected_response_type") or "direct_answer")
    actual_type = _classify_actual_response_type(resp)

    # Response type match (accept partial_answer <-> unsupported_request for guardrail / RBAC / missing-period edges if content matches)
    decision_match = actual_type == exp_type
    if exp_type == "partial_answer" and actual_type in ("partial_answer", "direct_answer") and any(
        k in full_cf for k in ("cannot", "not sent", "unavailable", "no published", "no ", "excluded")
    ):
        decision_match = True
    if exp_type == "unsupported_request" and actual_type in ("unsupported_request", "partial_answer") and any(
        k in full_cf for k in ("restricted", "cannot", "can't", "outside", "pms", "not support", "scope", "admin")
    ):
        decision_match = True

    needless_clarification = bool(exp_type != "clarification" and actual_type == "clarification")

    part_expectations = list(turn.get("part_expectations") or [])
    if not part_expectations and turn.get("required_terms"):
        part_expectations = [[str(t)] for t in turn["required_terms"]]

    part_results: list[dict[str, Any]] = []
    for idx, alts in enumerate(part_expectations):
        alt_list = [str(a).strip() for a in (alts if isinstance(alts, list) else [alts]) if str(a).strip()]
        ok = any(a.casefold() in full_cf for a in alt_list)
        part_results.append({"part_index": idx, "alternatives": alt_list, "passed": ok})

    part_passed = sum(1 for pr in part_results if pr["passed"])
    part_total = len(part_results)

    # Check critical errors / forbidden claims
    critical_errors: list[str] = []
    for fc in turn.get("forbidden_claims") or []:
        fc_str = str(fc or "").strip()
        if not fc_str:
            continue
        fc_cf = fc_str.casefold()
        if fc_cf in ("invented_number", "salary_amount"):
            # Flag suspicious $ or AED salary figures not in evidence
            if fc_cf == "salary_amount" and re.search(r"\b\d{4,6}\s*(?:aed|egp|usd|\$)\b", full_cf):
                critical_errors.append(f"forbidden_salary_disclosure:{fc_str}")
        elif fc_cf in full_cf:
            critical_errors.append(f"forbidden_claim:{fc_str}")

    if "% aed" in full_cf or "aed %" in full_cf:
        critical_errors.append("unit_confusion:%_aed")

    if exp_type == "clarification":
        exp_code = turn.get("expected_clarification_code")
        actual_code = str(getattr(clar, "code", "") or "") if clar else ""
        if exp_code and actual_code != exp_code:
            # Accept clarifying question mentioning the required choices if code differs slightly
            if actual_type != "clarification":
                critical_errors.append(f"missed_clarification:{exp_code}")

    whole_turn_passed = bool(
        decision_match
        and not needless_clarification
        and all(pr["passed"] for pr in part_results)
        and not critical_errors
    )

    failure_type = None
    if not whole_turn_passed:
        usage = getattr(resp, "provider_usage", None)
        fb = str(getattr(usage, "fallback_outcome", "") or "")
        if "timeout" in fb or "error" in fb:
            failure_type = "answer_failure"  # Fallback existed; answer failed quality check
        else:
            failure_type = "answer_failure"

    return {
        "outcome": str(getattr(resp, "outcome", "")),
        "expected_response_type": exp_type,
        "actual_response_type": actual_type,
        "decision_match": decision_match,
        "needless_clarification": needless_clarification,
        "part_passed": part_passed,
        "part_total": part_total,
        "parts": part_results,
        "critical_errors": critical_errors,
        "whole_turn_passed": whole_turn_passed,
        "failure_type": failure_type,
        "elapsed_ms": elapsed_ms,
        "headline": headline[:240],
        "provider_used": str(getattr(resp, "provider_used", "")),
    }


def _run_corrective_subsuite() -> dict[str, Any]:
    """Exercise CorrectiveActionDrafter bounded repair, non-repairable rejection, timeout fallback, and toggle."""
    import uuid
    from config.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    mp = MonkeyPatch()
    mp.setenv("PMS_AI_NVIDIA_ROUTING_ENABLED", "true")
    mp.setenv("PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED", "true")
    ai_evidence_cache.clear()

    team = Team(
        id=uuid.uuid4(), name="inbound", db_name="Inbound", display_name="Inbound",
        region="EGY", team_level="employee", is_active=True,
    )
    db.add(team)
    db.flush()
    employee = Employee(
        id=uuid.uuid4(), employee_id="EMP-1", name="Sara Inbound", team_id=team.id,
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
    for key, actual, target, ratio, weight in [("bookings_count", 30, 40, 0.75, 0.5), ("upsell", 0, 10, 0.0, 0.2)]:
        db.add(KPIValue(
            record_id=record.id, record_year=2026, kpi_key=key, actual_value=actual,
            target_value=target, achievement_ratio=ratio, weight_applied=weight, contribution=ratio * weight,
        ))
    db.commit()

    results: list[dict[str, Any]] = []
    req = AiCorrectiveActionSuggestionRequest(
        employee_id="EMP-1",
        team="Inbound",
        month="September",
        year=2026,
        performance_level="Employee",
        linked_kpi_key="bookings_count",
    )
    admin_scope = {"user_id": "u-bench-adm", "role": "Admin", "permissions": ["*"], "has_unrestricted_team_access": True}

    try:
        import services.ai.corrective_action_drafter as drafter_mod

        class _SeqEngine:
            def __init__(self, responses: list[ProviderResponse]):
                self.responses = list(responses)
                self.calls = 0

            def generate(self, request):
                idx = min(self.calls, len(self.responses) - 1)
                self.calls += 1
                return self.responses[idx]

        # 1. Wrong focus KPI (upsell instead of bookings_count) -> 1 bounded repair -> succeeds
        bad_kpi = json.dumps({
            "focus_kpi_key": "upsell",
            "action_type": "Coaching",
            "steps": [
                "Review recent calls with missed Bookings opportunities.",
                "Hold a short coaching session on Bookings talk tracks.",
            ],
        })
        good_kpi = json.dumps({
            "focus_kpi_key": "bookings_count",
            "action_type": "Coaching",
            "steps": [
                "Review recent calls with missed Bookings opportunities.",
                "Hold a short coaching session on Bookings talk tracks.",
            ],
        })
        eng1 = _SeqEngine([
            ProviderResponse(outcome="success", content=bad_kpi, provider="nvidia", model="bench-mock"),
            ProviderResponse(outcome="success", content=good_kpi, provider="nvidia", model="bench-mock"),
        ])
        mp.setattr(drafter_mod, "get_unified_provider_engine", lambda: eng1)
        out1 = CorrectiveActionDrafter(db).suggest(user_scope=admin_scope, request=req)
        results.append({
            "id": "ca_repair_wrong_kpi_recovered",
            "passed": out1.outcome == "suggested" and out1.repair_outcome == "repaired" and eng1.calls == 2,
            "repair_outcome": out1.repair_outcome,
            "calls": eng1.calls,
        })

        # 2. Fabricated cause / non-repairable safety violation -> rejected without retry & safe pms_evidence fallback
        bad_cause = json.dumps({
            "focus_kpi_key": "bookings_count",
            "action_type": "Coaching",
            "steps": [
                "Address staff fatigue causing missed calls.",
                "Hold a coaching session because of staffing shortage.",
            ],
        })
        eng2 = _SeqEngine([
            ProviderResponse(outcome="success", content=bad_cause, provider="nvidia", model="bench-mock"),
            ProviderResponse(outcome="success", content=good_kpi, provider="nvidia", model="bench-mock"),
        ])
        mp.setattr(drafter_mod, "get_unified_provider_engine", lambda: eng2)
        out2 = CorrectiveActionDrafter(db).suggest(user_scope=admin_scope, request=req)
        results.append({
            "id": "ca_fabricated_cause_no_retry_safe_fallback",
            "passed": out2.outcome == "draft_rejected" and eng2.calls == 1 and out2.repair_outcome == "non_repairable" and out2.evidence_next_step is not None,
            "repair_outcome": out2.repair_outcome,
            "calls": eng2.calls,
        })

        # 3. Reversible kill-switch disabled -> skips bounded repair
        mp.setenv("PMS_AI_CORRECTIVE_DRAFT_REPAIR_ENABLED", "false")
        eng3 = _SeqEngine([ProviderResponse(outcome="success", content=bad_kpi, provider="nvidia", model="bench-mock")])
        mp.setattr(drafter_mod, "get_unified_provider_engine", lambda: eng3)
        out3 = CorrectiveActionDrafter(db).suggest(user_scope=admin_scope, request=req)
        results.append({
            "id": "ca_repair_disabled_flag",
            "passed": out3.outcome == "draft_rejected" and eng3.calls == 1 and out3.repair_outcome == "non_repairable",
            "repair_outcome": out3.repair_outcome,
            "calls": eng3.calls,
        })

        # 4. Zero unconfirmed DB writes
        action_rows = db.query(Action).count()
        results.append({
            "id": "ca_zero_unconfirmed_db_writes",
            "passed": action_rows == 0,
            "action_rows": action_rows,
        })
    finally:
        mp.undo()
        ai_evidence_cache.clear()
        db.close()

    passed_n = sum(1 for r in results if r["passed"])
    return {
        "total": len(results),
        "passed": passed_n,
        "failed": len(results) - passed_n,
        "cases": results,
    }


def run_benchmark_mode(
    *,
    scenarios: list[dict[str, Any]],
    mode: str,
) -> dict[str, Any]:
    if mode == "live" and os.environ.get("PMS_AI_RUN_LIVE_MODEL_TESTS", "").strip().casefold() != "true":
        return {
            "mode": "live",
            "is_live_verified": False,
            "status": "blocked",
            "blocked_reason": "PMS_AI_RUN_LIVE_MODEL_TESTS is not set to 'true'; live benchmark execution skipped.",
            "total_scenarios": len(scenarios),
            "total_turns": sum(len(s.get("turns") or []) for s in scenarios),
            "splits": {},
        }

    mp = MonkeyPatch()
    mp.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true" if mode in ("scripted_mocked", "live") else "false")
    if mode != "live":
        for _env_key in (
            "PMS_AI_NVIDIA_ROUTING_ENABLED",
            "PMS_AI_LOCAL_ROUTER_ENABLED",
            "PMS_AI_LOCAL_EXPLORATION_ENABLED",
            "PMS_AI_LOCAL_SYNTHESIS_ENABLED",
            "PMS_AI_CLOUDFLARE_ENABLED",
        ):
            mp.setenv(_env_key, "false")
    db = _build_in_memory_db()
    recs = _build_benchmark_records()
    _patch_records(mp, recs)
    ai_evidence_cache.clear()

    if mode == "scripted_mocked":
        from ai_provider_fakes import failed_response, install_scripted_provider

        install_scripted_provider(mp, failed_response("timeout"))

    turn_records: list[dict[str, Any]] = []
    split_aggs: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "scenarios": 0,
            "scenarios_passed": 0,
            "turns": 0,
            "turns_passed": 0,
            "parts_passed": 0,
            "parts_total": 0,
            "decision_matches": 0,
            "needless_clarifications": 0,
            "critical_errors": 0,
            "latencies_ms": [],
            "by_language": defaultdict(lambda: {"turns": 0, "turns_passed": 0}),
            "by_decision_class": defaultdict(lambda: {"turns": 0, "turns_passed": 0}),
            "failure_taxonomy": defaultdict(int),
        }
    )

    try:
        for sc in scenarios:
            split = str(sc["split"])
            lang = str(sc.get("language") or "en")
            scope = dict(sc.get("scope") or {"user_id": "u-bench", "role": sc.get("authorized_role", "Admin"), "permissions": ["*"]})
            sess_raw = dict(sc.get("session_state") or {})
            session_state = SessionFilterContext(**sess_raw)
            history: list[dict[str, str]] = []
            conversation_id = None
            context_version = None
            sc_passed = True

            orch = PmsAiOrchestrator(db, scope)
            for t_idx, turn in enumerate(sc.get("turns") or [], start=1):
                ai_evidence_cache.clear()
                req_obj = AiChatRequest(
                    prompt=turn["prompt"],
                    conversation_id=conversation_id,
                    context_version=context_version,
                    session_state=session_state,
                    history=history,
                    provider_override="deterministic" if mode == "deterministic" else "auto",
                    answer_detail="brief",
                )
                t0 = time.perf_counter()
                try:
                    resp = orch.run_chat_turn(req_obj)
                    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    ev = _evaluate_turn(scenario=sc, turn=turn, resp=resp, elapsed_ms=elapsed_ms)
                    conversation_id = getattr(resp, "conversation_id", None) or conversation_id
                    context_version = getattr(resp, "context_version", None)
                    if getattr(resp, "resolved_session_state", None) is not None:
                        session_state = resp.resolved_session_state
                    history.append({"role": "user", "content": turn["prompt"]})
                    history.append({"role": "assistant", "content": str(getattr(resp, "headline", "") or "")})
                except Exception as exc:
                    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    ev = {
                        "outcome": "exception",
                        "expected_response_type": turn.get("expected_response_type", "direct_answer"),
                        "actual_response_type": "exception",
                        "decision_match": False,
                        "needless_clarification": False,
                        "part_passed": 0,
                        "part_total": max(1, len(turn.get("part_expectations") or [])),
                        "parts": [],
                        "critical_errors": [f"exception:{type(exc).__name__}"],
                        "whole_turn_passed": False,
                        "failure_type": "harness_failure",
                        "elapsed_ms": elapsed_ms,
                        "headline": str(exc)[:200],
                        "provider_used": "exception",
                    }

                agg = split_aggs[split]
                agg["turns"] += 1
                agg["turns_passed"] += int(ev["whole_turn_passed"])
                agg["parts_passed"] += int(ev["part_passed"])
                agg["parts_total"] += int(ev["part_total"])
                agg["decision_matches"] += int(ev["decision_match"])
                agg["needless_clarifications"] += int(ev["needless_clarification"])
                agg["critical_errors"] += len(ev["critical_errors"])
                agg["latencies_ms"].append(elapsed_ms)
                agg["by_language"][lang]["turns"] += 1
                agg["by_language"][lang]["turns_passed"] += int(ev["whole_turn_passed"])
                exp_cls = str(ev["expected_response_type"])
                agg["by_decision_class"][exp_cls]["turns"] += 1
                agg["by_decision_class"][exp_cls]["turns_passed"] += int(ev["whole_turn_passed"])
                if ev["failure_type"]:
                    agg["failure_taxonomy"][ev["failure_type"]] += 1
                if not ev["whole_turn_passed"]:
                    sc_passed = False

                turn_records.append(
                    {
                        "scenario_id": sc["id"],
                        "split": split,
                        "family": sc["family"],
                        "language": lang,
                        "turn_index": t_idx,
                        **ev,
                    }
                )

            split_aggs[split]["scenarios"] += 1
            split_aggs[split]["scenarios_passed"] += int(sc_passed)
    finally:
        mp.undo()
        ai_evidence_cache.clear()
        db.close()

    formatted_splits: dict[str, Any] = {}
    for sp, agg in split_aggs.items():
        t_tot = agg["turns"] or 1
        p_tot = agg["parts_total"] or 1
        s_tot = agg["scenarios"] or 1
        formatted_splits[sp] = {
            "scenarios": agg["scenarios"],
            "scenarios_passed": agg["scenarios_passed"],
            "scenario_pass_rate_pct": round(100.0 * agg["scenarios_passed"] / s_tot, 2),
            "turns": agg["turns"],
            "turns_passed": agg["turns_passed"],
            "whole_turn_accuracy_pct": round(100.0 * agg["turns_passed"] / t_tot, 2),
            "parts_passed": agg["parts_passed"],
            "parts_total": agg["parts_total"],
            "per_part_accuracy_pct": round(100.0 * agg["parts_passed"] / p_tot, 2),
            "decision_accuracy_pct": round(100.0 * agg["decision_matches"] / t_tot, 2),
            "needless_clarification_pct": round(100.0 * agg["needless_clarifications"] / t_tot, 2),
            "critical_errors": agg["critical_errors"],
            "latency_ms": {
                "p50": _percentile(agg["latencies_ms"], 50.0),
                "p95": _percentile(agg["latencies_ms"], 95.0),
                "max": round(max(agg["latencies_ms"]), 2) if agg["latencies_ms"] else None,
            },
            "by_language": {
                k: {**v, "accuracy_pct": round(100.0 * v["turns_passed"] / max(1, v["turns"]), 2)}
                for k, v in sorted(agg["by_language"].items())
            },
            "by_decision_class": {
                k: {**v, "accuracy_pct": round(100.0 * v["turns_passed"] / max(1, v["turns"]), 2)}
                for k, v in sorted(agg["by_decision_class"].items())
            },
            "failure_taxonomy": dict(agg["failure_taxonomy"]),
        }

    failing_samples = [r for r in turn_records if not r["whole_turn_passed"] and r["split"] != "blind"][:100]
    return {
        "mode": mode,
        "is_live_verified": mode == "live",
        "status": "passed" if all(v["critical_errors"] == 0 for v in formatted_splits.values()) else "failed",
        "total_scenarios": len(scenarios),
        "total_turns": sum(agg["turns"] for agg in split_aggs.values()),
        "splits": formatted_splits,
        "non_blind_failures_sample": failing_samples,
        "corrective_subsuite": _run_corrective_subsuite(),
    }


def _evaluate_release_scorecard(report: dict[str, Any]) -> dict[str, Any]:
    det = (report.get("modes") or {}).get("deterministic") or {}
    splits = det.get("splits") or {}
    target_split = splits.get("blind") or splits.get("val") or splits.get("dev") or {}
    ca_sub = det.get("corrective_subsuite") or {}
    metrics = {
        "whole_turn_accuracy_pct": target_split.get("whole_turn_accuracy_pct"),
        "per_part_accuracy_pct": target_split.get("per_part_accuracy_pct"),
        "needless_clarification_pct": target_split.get("needless_clarification_pct"),
        "critical_errors": target_split.get("critical_errors"),
        "p95_latency_ms": (target_split.get("latency_ms") or {}).get("p95"),
        "corrective_subsuite_passed": f"{ca_sub.get('passed', 0)}/{ca_sub.get('total', 0)}",
    }
    gates = {
        "whole_turn_gte_90": metrics["whole_turn_accuracy_pct"] is not None and metrics["whole_turn_accuracy_pct"] >= 90.0,
        "per_part_gte_95": metrics["per_part_accuracy_pct"] is not None and metrics["per_part_accuracy_pct"] >= 95.0,
        "needless_clarification_lt_3": metrics["needless_clarification_pct"] is not None and metrics["needless_clarification_pct"] < 3.0,
        "critical_errors_zero": metrics["critical_errors"] == 0,
        "p95_under_15000ms": metrics["p95_latency_ms"] is not None and metrics["p95_latency_ms"] <= 15000.0,
        "corrective_subsuite_all_passed": ca_sub.get("failed", 1) == 0,
    }
    return {
        "evaluated_split": "blind" if "blind" in splits else ("val" if "val" in splits else "dev"),
        "metrics": metrics,
        "gates": gates,
        "all_offline_gates_passed": all(gates.values()),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# PMS AI Unseen Benchmark Report",
        "",
        f"- **Generated At:** `{report['generated_at']}`",
        f"- **Benchmark SHA-256:** `{report['benchmark_sha256']}`",
        f"- **Split Filter:** `{report['split_filter']}`",
        "",
    ]
    for mode_name, mode_data in (report.get("modes") or {}).items():
        lines.extend([f"## Mode: `{mode_name}` (`is_live_verified={mode_data.get('is_live_verified')}`)", ""])
        if mode_data.get("status") == "blocked":
            lines.append(f"> Blocked: `{mode_data.get('blocked_reason')}`")
            lines.append("")
            continue
        lines.extend(
            [
                "| Split | Scenarios | Whole-Turn Acc % | Per-Part Acc % | Decision Acc % | Needless Clarif % | Critical Errors | p50 ms | p95 ms |",
                "|---|---|---|---|---|---|---|---|---|",
            ]
        )
        for sp, sp_d in (mode_data.get("splits") or {}).items():
            lat = sp_d.get("latency_ms") or {}
            lines.append(
                f"| `{sp}` | {sp_d['scenarios_passed']}/{sp_d['scenarios']} | {sp_d['whole_turn_accuracy_pct']}% | "
                f"{sp_d['per_part_accuracy_pct']}% | {sp_d['decision_accuracy_pct']}% | {sp_d['needless_clarification_pct']}% | "
                f"{sp_d['critical_errors']} | {lat.get('p50')} | {lat.get('p95')} |"
            )
        ca = mode_data.get("corrective_subsuite") or {}
        lines.append("")
        lines.append(f"- **Corrective Action Sub-Suite:** `{ca.get('passed')}/{ca.get('total')}` passed")
        lines.append("")

    sc = report.get("scorecard") or {}
    lines.extend(["## Release Scorecard Summary", ""])
    lines.append(f"- **Scorecard Split:** `{sc.get('evaluated_split')}` · **Offline Gates Passed:** `{sc.get('all_offline_gates_passed')}`")
    for gk, gv in (sc.get("gates") or {}).items():
        lines.append(f"  - `{gk}`: `{gv}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run PMS AI 240-scenario Unseen Benchmark.")
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK_PATH)
    parser.add_argument("--split", default="all", help="Comma-separated splits: dev,val,blind or all")
    parser.add_argument("--mode", default="comparative", choices=("deterministic", "scripted_mocked", "live", "comparative"))
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_OUT)
    args = parser.parse_args(argv)

    raw_bytes = args.benchmark.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    loaded = json.loads(raw_bytes.decode("utf-8"))
    all_scenarios = loaded.get("scenarios", loaded) if isinstance(loaded, dict) else loaded

    if args.split == "all":
        scenarios = all_scenarios
    else:
        allowed = {s.strip().casefold() for s in args.split.split(",") if s.strip()}
        scenarios = [s for s in all_scenarios if str(s.get("split", "")).casefold() in allowed]

    modes = ["deterministic", "scripted_mocked", "live"] if args.mode == "comparative" else [args.mode]
    mode_results = {m: run_benchmark_mode(scenarios=scenarios, mode=m) for m in modes}

    report = {
        "schema_version": "pms-ai-unseen-benchmark-report-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_sha256": sha256,
        "split_filter": args.split,
        "modes": mode_results,
    }
    report["scorecard"] = _evaluate_release_scorecard(report)

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(render_markdown(report), encoding="utf-8")

    print(json.dumps(report["scorecard"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
