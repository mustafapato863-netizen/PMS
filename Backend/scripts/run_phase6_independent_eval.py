"""Evaluate a frozen set of synthetic PMS chat turns.

The reference benchmark covers:
- Egypt & UAE across published Employee, Managerial, and Corporate levels
- Multi-turn hierarchy drill-downs (dept -> team -> top 3, second one, Marketing roles -> employee, overrides)
- Unfamiliar natural-English paraphrases & catalog discovery
- Lower-is-better KPIs, ties, branch comparisons, scoring rules, What-If, HR boundary
- Missing/unpublished months, ambiguity clarifications, off-topic/greeting boundaries
- Critical RBAC isolation (self-only, scoped manager, mid-conversation revocation)
- Provider failure fallback & idempotent replay

Runs the exact same fixture & scorer in:
- `baseline` (deterministic rules)
- `mocked` (scripted model-led + injected outage)
- `live` (configured live NVIDIA / provider via UnifiedProviderEngine)

Scores the FIRST observed response per turn (never replaces failures with retries).
Run from the repo root:
    python Backend/scripts/run_phase6_independent_eval.py --suite all --out .tmp/pms-ai-qa.json --markdown .tmp/pms-ai-qa.md
Use --suite conversation --session <session-id> to reproduce a single journey.
Add --fail-on-issues for a nonzero exit code after the reports are saved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.environment import load_project_environment
load_project_environment(str(BACKEND_DIR))

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import AiChatMessage, AiChatRequest, SessionFilterContext
from models.models import Action
from models.schemas import CallsData, EvaluationData, GeoBreakdown, GeoData, PerformanceRecord
from services.ai import provider_engine as pe_mod
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator
from services.dashboard_record_service import DashboardRecordService
from services.database_record_source import DatabaseRecordSource

FIXTURE_PATH = BACKEND_DIR / "tests" / "fixtures" / "ai_phase6_independent_holdout_v1.json"
CONVERSATION_FIXTURE = FIXTURE_PATH.with_name("ai_qa_conversation_v1.json")
EXACT_PARAPHRASES_FIXTURE = FIXTURE_PATH.with_name("ai_qa_exact_paraphrases_v1.json")


def _mk_rec(
    emp_id: str,
    name: str,
    team: str,
    region: str,
    score: float,
    *,
    month: str = "September",
    year: int = 2026,
    position: str = "Specialist",
    branch: str = "dubai",
    level: str = "Employee",
    waiting: float | None = None,
    booking_rate: float | None = None,
    quality_errors: float | None = None,
    bookings_dubai: int = 0,
    bookings_sharjah: int = 0,
    bookings_ajman: int = 0,
) -> PerformanceRecord:
    kpis: list[dict[str, Any]] = [
        {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": score, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
    ]
    team_default_kpi = {
        "Submission": ("submission_within_due_date", "Submission Within Due Date", 100.0, "%", "higher_better"),
        "Sales": ("OPCensus", "OP Census Ach", 100.0, "number", "higher_better"),
        "CSR": ("Queries", "Queries Handled", 100.0, "%", "higher_better"),
        "Pharmacy": ("TenderCompliance", "Tender Compliance", 100.0, "%", "higher_better"),
    }.get(team)
    if team_default_kpi is not None:
        k_key, k_label, k_tgt, k_unit, k_dir = team_default_kpi
        kpis.append({"kpi_key": k_key, "label": k_label, "actual_value": score, "target_value": k_tgt, "unit": k_unit, "direction": k_dir})
    if waiting is not None:
        kpis.append({"kpi_key": "waitingtime", "label": "Waiting Time", "actual_value": waiting, "target_value": 5.0, "unit": "min", "direction": "lower_better"})
    if booking_rate is not None:
        kpis.append({"kpi_key": "Booking", "label": "Booking Rate", "actual_value": booking_rate, "target_value": 30.0, "unit": "%", "direction": "higher_better"})
    if quality_errors is not None:
        kpis.append({"kpi_key": "QualityErrors", "label": "Quality Errors", "actual_value": quality_errors, "target_value": 3.0, "unit": "%", "direction": "lower_better"})
    geo = None
    calls = None
    if bookings_dubai or bookings_sharjah or bookings_ajman:
        tot_b = bookings_dubai + bookings_sharjah + bookings_ajman
        kpis.append({"kpi_key": "bookings_count", "label": "Bookings Count", "actual_value": tot_b, "target_value": 100, "unit": "count", "direction": "higher_better"})
        geo = GeoData(
            bookings=GeoBreakdown(dubai=bookings_dubai, sharjah=bookings_sharjah, ajman=bookings_ajman, clinics=0),
            attended=GeoBreakdown(dubai=int(bookings_dubai * 0.8), sharjah=int(bookings_sharjah * 0.8), ajman=int(bookings_ajman * 0.8), clinics=0),
        )
        calls = CallsData(inbound=tot_b * 3, total_handled=tot_b * 3, abandoned=5)
    extra: dict[str, Any] = {}
    if calls is not None:
        extra["calls"] = calls
    if geo is not None:
        extra["geo"] = geo
    return PerformanceRecord(
        id=f"p6_{team}_{emp_id}_{year}_{month[:3]}_{level}",
        employee_id=emp_id,
        employee_name=name,
        team=team,
        position=position,
        region=region,
        branch=branch,
        raw_data={"Branch": branch.capitalize()},
        month=month,
        year=year,
        performance_level=level,
        status="On Track" if score >= 80 else "Below Target",
        evaluation=EvaluationData(score=score, grade="A" if score >= 90 else ("B" if score >= 80 else "C")),
        kpi_values=kpis,
        **extra,
    )


def build_synthetic_holdout_records() -> list[PerformanceRecord]:
    """Deterministic, zero-PII synthetic dataset covering EGY/UAE and Employee/Managerial/Corporate."""
    return [
        # --- EGY September 2026 (Employee) ---
        # Call Center: Inbound avg = (96+94+92+84)/4 = 91.5, Outbound avg = (89+89)/2 = 89.0 -> CC dept avg = 544/6 = 90.67
        _mk_rec("H-IN-01", "Nadia Mansour", "Inbound", "EGY", 96.0, waiting=3.4, booking_rate=34.0, bookings_dubai=80, bookings_sharjah=40, bookings_ajman=20),
        _mk_rec("H-IN-02", "Karim Fawzy", "Inbound", "EGY", 94.0, waiting=4.8, booking_rate=31.0, bookings_dubai=60, bookings_sharjah=30, bookings_ajman=15),
        _mk_rec("H-IN-03", "Hala Barakat", "Inbound", "EGY", 92.0, waiting=5.2, booking_rate=29.0, bookings_dubai=50, bookings_sharjah=25, bookings_ajman=10),
        _mk_rec("H-IN-04", "Rami Khoury", "Inbound", "EGY", 84.0, waiting=7.1, booking_rate=22.0, bookings_dubai=30, bookings_sharjah=15, bookings_ajman=5),
        # Outbound tied top performers (both 89.0!)
        _mk_rec("H-OUT-01", "Dina Soliman", "Outbound", "EGY", 89.0, booking_rate=28.0),
        _mk_rec("H-OUT-02", "Omar Haddad", "Outbound", "EGY", 89.0, booking_rate=27.0),
        # Human Resources: avg = 95.0 (Leads EGY Sep 2026 Employee departments!)
        _mk_rec("H-HR-01", "Tala Mansoor", "Human Resources", "EGY", 95.0, position="HR Specialist"),
        # Marketing (single team, multiple measured roles): avg = (98.0+90.0+76.0)/3 = 88.0
        _mk_rec("H-MKT-01", "Fadi Nassar", "Marketing", "EGY", 98.0, position="Creative Director"),
        _mk_rec("H-MKT-02", "Yara Qasem", "Marketing", "EGY", 90.0, position="Content Writer"),
        _mk_rec("H-MKT-03", "Samir Gamil", "Marketing", "EGY", 76.0, position="Media Buyer"),
        # RCM EGY: Coding EGY avg = 72.0
        _mk_rec("H-RCM-01", "Lina Darwish", "Coding EGY", "EGY", 72.0, quality_errors=4.2),
        # --- EGY September 2026 (Managerial) ---
        _mk_rec("H-MGR-01", "Ziad Farag", "Pre-Approvals IP", "EGY", 91.2, position="Team Manager", level="Managerial"),
        # --- EGY August 2026 (Employee) ---
        _mk_rec("H-IN-01", "Nadia Mansour", "Inbound", "EGY", 89.0, month="August", waiting=5.4, booking_rate=28.0),
        _mk_rec("H-MKT-01", "Fadi Nassar", "Marketing", "EGY", 92.0, month="August", position="Creative Director"),
        _mk_rec("H-MKT-02", "Yara Qasem", "Marketing", "EGY", 84.0, month="August", position="Content Writer"),
        _mk_rec("H-MKT-03", "Samir Gamil", "Marketing", "EGY", 70.0, month="August", position="Media Buyer"),  # Aug MKT avg = 82.0 (+6.0 pp to Sep 88.0)
        # --- UAE August 2026 (Employee; NO UAE September 2026!) ---
        _mk_rec("H-UAE-01", "Bilal Al-Mansoori", "Coding", "UAE", 97.0, month="August", branch="dubai", quality_errors=0.012),
        _mk_rec("H-UAE-02", "Noora Al-Ali", "Submission", "UAE", 93.0, month="August", branch="sharjah", quality_errors=0.018),
        _mk_rec("H-UAE-03", "Majed Al-Suwaidi", "Sales", "UAE", 78.0, month="August", branch="dubai"),
        _mk_rec("H-UAE-04", "Reem Al-Kaabi", "Sales", "UAE", 74.0, month="August", branch="sharjah"),  # Sales UAE Aug avg = 76.0
        _mk_rec("H-UAE-05", "Saeed Al-Dhaheri", "CSR", "UAE", 64.0, month="August", branch="ajman"),
        # --- UAE June 2026 (Pharmacy branches + Corporate) ---
        _mk_rec("H-PH-01", "Aisha Al-Nuaimi", "Pharmacy", "UAE", 88.5, month="June", branch="dubai"),
        _mk_rec("H-PH-02", "Khaled Al-Zaabi", "Pharmacy", "UAE", 81.0, month="June", branch="sharjah"),
        _mk_rec("H-PH-03", "Mariam Al-Shamsi", "Pharmacy", "UAE", 79.0, month="June", branch="ajman"),
        _mk_rec("H-CORP-01", "Corporate Executive", "Finance", "UAE", 87.5, month="June", branch="dubai", level="Corporate"),
    ]


def load_frozen_fixture(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    # Keep the digest stable across Git checkouts with different newline settings.
    contents = path.read_bytes().replace(b"\r\n", b"\n")
    fixture = json.loads(contents)
    if (
        hashlib.sha256(contents).hexdigest() != manifest["fixture_sha256"]
        or len(fixture["sessions"]) != manifest["session_count"]
        or sum(len(session["turns"]) for session in fixture["sessions"]) != manifest["turn_count"]
    ):
        raise ValueError(f"Frozen benchmark manifest mismatch: {path}")
    return fixture, manifest


_NUMBER = r"(?<![\w.,+\-])([+\-−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?!\d|[.,]\d)"
_UNITS = {
    "%": r"\s*(?:%|percent\b)",
    "min": r"\s*(?:mins?\b|minutes?\b)",
    "pts": r"\s*(?:pp\b|pts?\b|(?:percentage )?points?\b)",
}


def _contains_value(text: str, expected: str | float, unit: str | None = None) -> bool:
    suffix = _UNITS[unit] if unit else r"(?!\w)"
    return any(
        Decimal(match.group(1).replace(",", "").replace("−", "-")) == Decimal(str(expected))
        for match in re.finditer(_NUMBER + suffix, text, flags=re.IGNORECASE)
    )


def _contains_token(text: str, token: str) -> bool:
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", token):
        return _contains_value(text, token)
    return token.casefold() in text.casefold()


def _planner_tools(content: str) -> list[str]:
    try:
        plan = json.loads(content)
    except (TypeError, ValueError):
        return []
    if not isinstance(plan, dict) or plan.get("response_type") != "tool_call":
        return []
    calls = plan.get("tool_calls") or [plan]
    return [
        call["tool_name"] for call in calls
        if isinstance(call, dict) and isinstance(call.get("tool_name"), str)
    ] if isinstance(calls, list) else []


def _score_turn(turn: dict[str, Any], resp: Any, *, replay_extra_calls: int | None = None) -> tuple[bool, list[str], bool, list[str]]:
    sem_failures: list[str] = []
    crit_failures: list[str] = []
    text = "\n".join([resp.headline or "", *(resp.narrative_bullets or []), *(resp.detail_bullets or [])])
    lower = text.casefold()
    exp_out = turn["expected_outcome"]

    if exp_out == "unavailable_or_empty":
        if resp.outcome not in ("unavailable_data", "answer"):
            sem_failures.append(f"outcome {resp.outcome!r} not in unavailable_data/answer")
        elif resp.outcome == "answer" and not any(k in lower for k in ("no ", "unavailable", "unpublished", "not available", "not found", "missing")):
            sem_failures.append(f"expected unavailable/empty disclosure, got: {resp.headline!r}")
    elif exp_out == "any_safe":
        if resp.outcome not in ("answer", "clarification", "unavailable_data", "unsupported_request"):
            sem_failures.append(f"unexpected outcome {resp.outcome!r}")
    elif resp.outcome != exp_out:
        sem_failures.append(f"outcome {resp.outcome!r} != {exp_out!r} (H={resp.headline!r})")
        if turn.get("critical_auth"):
            crit_failures.append(f"critical_auth_outcome_mismatch:{resp.outcome}!={exp_out}")

    for group in turn.get("must_contain_any", []):
        if not any(_contains_token(text, tok) for tok in group):
            sem_failures.append(f"missing any of {group} in {text[:220]!r}")

    for forbidden in turn.get("must_not_contain", []):
        if forbidden.casefold() in lower:
            sem_failures.append(f"forbidden token {forbidden!r} appeared in {text[:220]!r}")
            if turn.get("critical_auth") or exp_out == "unavailable_or_empty" or turn.get("required_facts"):
                crit_failures.append(f"critical_forbidden_leak:{forbidden}")

    st = resp.resolved_session_state
    for key, expected in (turn.get("critical_scope") or {}).items():
        actual = getattr(st, key, None)
        if actual is None or str(actual).casefold() != str(expected).casefold():
            crit_failures.append(f"critical_{key}_mismatch:{actual}!={expected}")

    for value in turn.get("critical_numbers", []):
        if not _contains_value(text, value):
            crit_failures.append(f"critical_number_missing:{value}")
    for fact in turn.get("required_facts", []):
        # Bind a named value within one claim, so a number attached to a different
        # person or metric cannot satisfy the oracle.
        subject = fact.get("subject")
        claims = re.split(r"[\n;]|(?<=[.!?])\s+", text)
        candidates = [claim for claim in claims if not subject or subject.casefold() in claim.casefold()]
        if subject and fact.get("ranked"):
            name_end = re.escape(subject) + r"\s*(?::|—|–|=|-|\(|at\b|with\b)\s*"
            candidates = [
                match.group(1) for claim in candidates
                for match in re.finditer(name_end + r"([^\n,;)]*)", claim, flags=re.IGNORECASE)
            ]
        if not any(_contains_value(claim, fact["value"], fact.get("unit")) for claim in candidates):
            crit_failures.append(f"critical_fact_missing:{fact}")

    ranks = turn.get("required_ranks", [])
    offsets = [lower.find(entity.casefold()) for entity in ranks]
    if -1 in offsets or (not turn.get("allow_rank_ties") and offsets != sorted(offsets)):
        crit_failures.append(f"critical_rank_entities_missing_or_out_of_order:{ranks}")

    modes = turn.get("required_tools", [])
    if modes and not any(
        (call.tool_name in modes or (
            call.tool_name == "get_kpi_diagnosis" and "get_kpi_diagnosis_and_trends" in modes
        ))
        and call.records_evaluated > 0 for call in resp.tool_calls
    ):
        crit_failures.append(f"missing successful analytical tool from {modes}")

    if turn.get("idempotent_replay_check") and replay_extra_calls != 0:
        crit_failures.append(f"idempotent_replay_not_verified:{replay_extra_calls}")

    checks = turn.get("checks", {})
    if checks.get("no_tools") and resp.tool_calls:
        sem_failures.append("routing: a conversation-only turn executed analytical tools")
    if checks.get("rank_entity"):
        confirmed = getattr(st, "last_confirmed_query", None)
        entity = next((result.entity for result in (confirmed.ranking_results if confirmed else [])), None)
        if entity != checks["rank_entity"]:
            crit_failures.append(f"identity: ranked {entity!r}, expected {checks['rank_entity']!r}")
    if checks.get("proposal"):
        proposal = getattr(resp, "action_proposal", None)
        for key, expected in checks["proposal"].items():
            actual = getattr(proposal, key, None)
            if actual != expected:
                crit_failures.append(f"proposal: {key} was {actual!r}, expected {expected!r}")
    if checks.get("no_proposal") and getattr(resp, "action_proposal", None):
        crit_failures.append("proposal: a read request created a proposal")
    if checks.get("distinct_text"):
        parts = [
            re.sub(r"[\W_]+", " ", item.casefold()).strip()
            for item in re.split(r"\n|(?<=[.!?])\s+", text) if item.strip()
        ]
        if any(n > 1 for n in Counter(filter(None, parts)).values()):
            sem_failures.append("format: repeated sentence in the answer")
    if "max_words" in checks and len(text.split()) > checks["max_words"]:
        sem_failures.append(f"format: {len(text.split())} words exceeds the {checks['max_words']}-word limit")
    if checks.get("forbidden_response"):
        response_text = resp.model_dump_json(exclude={"resolved_session_state", "structured_query", "validated_plan_v2"}).casefold()
        for term in checks["forbidden_response"]:
            if term.casefold() in response_text:
                crit_failures.append(f"authorization: forbidden data in response or evidence: {term}")

    sem_ok = len(sem_failures) == 0 and len(crit_failures) == 0
    crit_ok = len(crit_failures) == 0
    return sem_ok, sem_failures, crit_ok, crit_failures


def run_eval_mode(
    mode: str, *, fixture_path: Path = FIXTURE_PATH, provider: str = "nvidia",
    nvidia_model: str = "nvidia/nemotron-3.5-super-vl-120b-a12b", pacing_ms: int = 0, thinking_level: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    fixture, _ = load_frozen_fixture(fixture_path)
    sessions = [session for session in fixture["sessions"] if session_id in (None, session["id"])]
    if not sessions:
        raise ValueError(f"Unknown evaluation session: {session_id}")
    records = build_synthetic_holdout_records()

    saved_env = {k: os.environ.get(k) for k in (
        "PMS_AI_MODEL_LED_PILOT_ENABLED", "PMS_AI_PRIMARY_PROVIDER", "PMS_AI_FALLBACK_ENABLED",
        "NVIDIA_FEEDBACK_MODEL", "PMS_AI_PROVIDER_TIMEOUT_SECONDS", "PMS_AI_SYNTHESIS_ENABLED",
        "PMS_AI_TASK_ROUTING_ENABLED", "PMS_AI_INTENT_ENABLED", "PMS_AI_TURN_DEADLINE_SECONDS", "PMS_AI_NVIDIA_REASONING_EFFORT",
    )}
    if mode == "live":
        os.environ["PMS_AI_MODEL_LED_PILOT_ENABLED"] = "true"
        os.environ["PMS_AI_PRIMARY_PROVIDER"] = "cloudflare" if provider == "split" else provider
        os.environ["PMS_AI_FALLBACK_ENABLED"] = "true" if provider == "split" else "false"
        os.environ["PMS_AI_TASK_ROUTING_ENABLED"] = "true" if provider == "split" else "false"
        os.environ["NVIDIA_FEEDBACK_MODEL"] = nvidia_model
        os.environ["PMS_AI_PROVIDER_TIMEOUT_SECONDS"] = "20.0"
        os.environ["PMS_AI_TURN_DEADLINE_SECONDS"] = "30.0"
        os.environ["PMS_AI_SYNTHESIS_ENABLED"] = "true"
        os.environ["PMS_AI_INTENT_ENABLED"] = "true"
        if thinking_level:
            os.environ["PMS_AI_NVIDIA_REASONING_EFFORT"] = thinking_level.lower()
    elif mode == "mocked":
        os.environ["PMS_AI_MODEL_LED_PILOT_ENABLED"] = "true"
        os.environ["PMS_AI_PROVIDER_TIMEOUT_SECONDS"] = "10.0"
        os.environ["PMS_AI_SYNTHESIS_ENABLED"] = "true"
    else:
        os.environ["PMS_AI_MODEL_LED_PILOT_ENABLED"] = "false"
        os.environ["PMS_AI_SYNTHESIS_ENABLED"] = "false"
        os.environ["PMS_AI_INTENT_ENABLED"] = "false"

    orig_engine_default = pe_mod._default_engine
    pe_mod.reset_unified_provider_engine()

    orig_get_all = DatabaseRecordSource.get_all
    orig_list_records = DashboardRecordService.list_records
    orig_list_analysis = DashboardRecordService.list_analysis_records
    orig_list_index = DashboardRecordService.list_record_index
    DatabaseRecordSource.get_all = lambda *a, **kw: list(records)
    DashboardRecordService.list_records = lambda *a, **kw: list(records)
    DashboardRecordService.list_analysis_records = lambda *a, **kw: list(records)
    DashboardRecordService.list_record_index = lambda *a, **kw: None

    # Mocked deterministic provider shim for mocked mode
    if mode == "mocked":
        from tests.ai_provider_fakes import ScriptedProviderEngine, failed_response
        pe_mod._default_engine = ScriptedProviderEngine([failed_response("provider_unavailable")], provider="nvidia")

    try:
        eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=eng)
        SessionT = sessionmaker(bind=eng)
        db = SessionT()
        ai_evidence_cache.clear()

        turn_results: list[dict[str, Any]] = []
        latencies_cold: list[float] = []
        total_provider_calls = 0
        total_tokens = 0
        total_cost_usd = 0.0
        unpriced_calls = 0
        model_led_turns = 0
        fallback_turns = 0
        deterministic_turns = 0

        for sess in sessions:
            scope = dict(sess.get("scope_override") or {
                "role": sess.get("role", "Admin"),
                "user_id": f"eval-{sess['id']}",
                "has_unrestricted_team_access": True,
            })
            orch = PmsAiOrchestrator(db, scope)
            init_state = SessionFilterContext(**(sess.get("initial_state") or {}))
            state = init_state
            conv_id: str | None = None
            history: list[AiChatMessage] = []
            saved_states: dict[int, tuple[str | None, SessionFilterContext, list[AiChatMessage]]] = {}
            uses_history = sess.get("use_history", False)

            for idx, turn in enumerate(sess["turns"], start=1):
                if sess.get("independent_turns"):
                    state = init_state.model_copy(deep=True)
                    conv_id = None
                    history = []
                if turn.get("reset_to_turn") and turn["reset_to_turn"] in saved_states:
                    conv_id, state, history = saved_states[turn["reset_to_turn"]]
                if turn.get("narrow_scope_to"):
                    orch = PmsAiOrchestrator(db, dict(turn["narrow_scope_to"]))

                req_provider_override = "deterministic" if mode == "baseline" else "auto"
                client_req_id = f"idem-{mode}-{turn['id']}" if turn.get("idempotent_replay_check") else None

                # Optional provider outage injection on t52
                saved_def = pe_mod._default_engine
                if turn.get("inject_provider_timeout") and mode != "baseline":
                    from tests.ai_provider_fakes import ScriptedProviderEngine, failed_response
                    pe_mod._default_engine = ScriptedProviderEngine([failed_response("timeout")], provider="nvidia")

                t0 = time.perf_counter()
                engine = pe_mod.get_unified_provider_engine()
                generate_request = engine.generate
                requested_tools: list[str] = []
                provider_requests = []
                checks = turn.get("checks", {})
                action_count = db.scalar(select(func.count()).select_from(Action)) if checks.get("no_action_write") else None
                request = AiChatRequest(
                    conversation_id=conv_id,
                    prompt=turn["prompt"],
                    session_state=state,
                    origin=sess.get("origin"),
                    page_context=turn.get("page_context") or sess.get("page_context"),
                    history=history[-12:] if uses_history else [],
                    provider_override=req_provider_override,
                    answer_detail="brief",
                    client_request_id=client_req_id,
                )

                def capture_planner(request):
                    provider_response = generate_request(request)
                    provider_requests.append({
                        "purpose": request.purpose, "role": request.task_role,
                        "provider": provider_response.provider, "model": provider_response.model,
                        "outcome": provider_response.outcome,
                        "estimated_cost_usd": provider_response.estimated_cost_usd,
                        "tokens": provider_response.usage.total_tokens,
                    })
                    if request.purpose in {"model_led_router", "model_led_discovery"} and provider_response.is_success:
                        requested_tools.extend(_planner_tools(provider_response.content))
                    return provider_response

                try:
                    with patch.object(engine, "generate", side_effect=capture_planner):
                        resp = orch.run_chat_turn(request.model_copy(deep=True))
                except Exception as exc:
                    db.rollback()
                    elapsed = round((time.perf_counter() - t0) * 1000.0, 1)
                    latencies_cold.append(elapsed)
                    turn_results.append({
                        "id": turn["id"], "session": sess["id"], "family": sess["family"], "prompt": turn["prompt"],
                        "outcome": "execution_error", "headline": "", "bullets": [], "scope": {},
                        "tool_calls": [], "expected_model_plan": bool(turn.get("expected_model_plan")),
                        "model_plan_executed": False, "model_selected_tool_executed": False,
                        "elapsed_ms": elapsed, "semantic_passed": False, "critical_passed": False,
                        "semantic_failures": [], "critical_failures": [f"runtime: {type(exc).__name__}"],
                        "expectations": {key: value for key, value in turn.items() if key not in ("id", "prompt")},
                    })
                    continue
                finally:
                    if turn.get("inject_provider_timeout") and mode != "baseline":
                        pe_mod._default_engine = saved_def

                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                latencies_cold.append(elapsed_ms)
                if mode == "live" and pacing_ms > 0 and resp.provider_usage and int(resp.provider_usage.provider_calls or 0) > 0:
                    time.sleep(pacing_ms / 1000.0)

                # Idempotent replay verification (separate from first response)
                replay_extra_calls: int | None = None
                if turn.get("idempotent_replay_check") and client_req_id:
                    engine = pe_mod.get_unified_provider_engine()
                    with patch.object(engine, "generate", wraps=engine.generate) as generate:
                        r_rep = orch.run_chat_turn(request.model_copy(update={"conversation_id": resp.conversation_id}))
                    if r_rep.model_dump() == resp.model_dump():
                        replay_extra_calls = generate.call_count

                if not sess.get("independent_turns"):
                    conv_id = resp.conversation_id
                    state = resp.resolved_session_state or state
                    if uses_history:
                        history = [
                            *history, AiChatMessage(role="user", content=turn["prompt"]),
                            AiChatMessage(role="assistant", content=resp.headline),
                        ]
                    saved_states[idx] = (conv_id, state.model_copy(deep=True), history)

                pu = resp.provider_usage
                p_calls = int(pu.provider_calls or 0) if pu else 0
                in_tok = int(pu.input_tokens or 0) if pu else 0
                out_tok = int(pu.output_tokens or 0) if pu else 0
                known_cost = sum(r["estimated_cost_usd"] for r in provider_requests if r["estimated_cost_usd"] is not None)
                unknown = sum(r["estimated_cost_usd"] is None for r in provider_requests)
                if not provider_requests and p_calls:
                    unknown = int(pu.estimated_cost_usd is None)
                    known_cost = pu.estimated_cost_usd or 0.0
                unpriced_calls += unknown
                cost_usd = None if unknown else known_cost
                total_provider_calls += p_calls
                total_tokens += (in_tok + out_tok)
                total_cost_usd += known_cost

                if resp.answer_source == "model_synthesis":
                    model_led_turns += 1
                elif resp.answer_source == "fallback":
                    fallback_turns += 1
                else:
                    deterministic_turns += 1

                sem_ok, sem_fails, crit_ok, crit_fails = _score_turn(turn, resp, replay_extra_calls=replay_extra_calls)
                if action_count is not None and db.scalar(select(func.count()).select_from(Action)) != action_count:
                    crit_fails.append("authorization: chat changed corrective actions before confirmation")
                    sem_ok = crit_ok = False
                model_plan_executed = (
                    bool(pu and pu.route_used == "model_led_pilot")
                    and any(
                        call.tool_name != "discover_pms_catalog" and call.records_evaluated > 0
                        for call in resp.tool_calls
                    )
                )
                turn_results.append({
                    "id": turn["id"],
                    "session": sess["id"],
                    "family": sess["family"],
                    "prompt": turn["prompt"],
                    "outcome": resp.outcome,
                    "answer_source": resp.answer_source,
                    "provider_used": resp.provider_used,
                    "model_used": resp.model_used,
                    "route_used": pu.route_used if pu else None,
                    "provider_fallback_outcome": pu.fallback_outcome if pu else None,
                    "tool_calls": [call.tool_name for call in resp.tool_calls],
                    "executed_reads": [
                        {"tool": call.tool_name, "rows": call.records_evaluated,
                         "filters": {k: v for k, v in call.arguments.items()
                                     if k in ("entity", "metric_id", "sort_order", "limit", "period", "region", "branch",
                                              "team", "department", "performance_level", "group_by", "score_threshold")}}
                        for call in resp.tool_calls
                    ],
                    "model_selected_tools": requested_tools,
                    "model_selected_tool_executed": model_plan_executed and any(
                        call.tool_name in requested_tools and call.records_evaluated > 0
                        for call in resp.tool_calls
                    ),
                    "model_plan_executed": model_plan_executed,
                    "expected_model_plan": bool(turn.get("expected_model_plan")),
                    "provider_calls": p_calls,
                    "provider_requests": provider_requests,
                    "tokens": in_tok + out_tok,
                    "cost_usd": cost_usd,
                    "elapsed_ms": elapsed_ms,
                    "semantic_passed": sem_ok,
                    "critical_passed": crit_ok,
                    "semantic_failures": sem_fails,
                    "critical_failures": crit_fails,
                    "headline": resp.headline,
                    "bullets": resp.narrative_bullets,
                    "expectations": {key: value for key, value in turn.items() if key not in ("id", "prompt")},
                    "scope": {
                        key: getattr(resp.resolved_session_state, key, None)
                        for key in ("region", "function", "team", "position", "branch", "performance_level", "month", "year")
                    },
                })

        # Measure warm cache latency on 5 representative turns (deterministic/cached evidence)
        warm_latencies: list[float] = []
        warm_orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "eval-s01_egy_dept_team_emp", "has_unrestricted_team_access": True})
        for wp in (
            "Which department had the highest average employee score in Egypt in September 2026?",
            "Which two teams performed best in Call Center in Egypt in September 2026?",
            "What was the average employee PMS score for Sales in the UAE in August 2026?",
            "What is the best team in Marketing in Egypt in September 2026?",
            "What was Nadia Mansour's Waiting Time in September 2026?",
        ):
            tw0 = time.perf_counter()
            warm_orch.run_chat_turn(
                AiChatRequest(
                    prompt=wp,
                    session_state=SessionFilterContext(month="September", year=2026),
                    provider_override="deterministic",
                )
            )
            warm_latencies.append(round((time.perf_counter() - tw0) * 1000.0, 1))

        db.close()

        denom = len(turn_results)
        sem_pass = sum(1 for r in turn_results if r["semantic_passed"])
        crit_pass = sum(1 for r in turn_results if r["critical_passed"])
        sorted_lat = sorted(latencies_cold)
        p50 = sorted_lat[len(sorted_lat) // 2] if sorted_lat else 0.0
        p95 = sorted_lat[min(len(sorted_lat) - 1, int(len(sorted_lat) * 0.95))] if sorted_lat else 0.0
        sorted_warm = sorted(warm_latencies)
        warm_p50 = sorted_warm[len(sorted_warm) // 2] if sorted_warm else 0.0
        warm_p95 = sorted_warm[-1] if sorted_warm else 0.0

        by_family: dict[str, dict[str, Any]] = {}
        for r in turn_results:
            fam = by_family.setdefault(r["family"], {"total": 0, "semantic_passed": 0, "critical_passed": 0})
            fam["total"] += 1
            if r["semantic_passed"]:
                fam["semantic_passed"] += 1
            if r["critical_passed"]:
                fam["critical_passed"] += 1
        for fam in by_family.values():
            fam["semantic_pct"] = round(fam["semantic_passed"] / fam["total"] * 100.0, 2)
            fam["critical_pct"] = round(fam["critical_passed"] / fam["total"] * 100.0, 2)

        return {
            "mode": mode,
            "provider": provider if mode == "live" else mode,
            "model": nvidia_model if mode == "live" else mode,
            "denominator": denom,
            "semantic_passed": sem_pass,
            "semantic_pct": round(sem_pass / denom * 100.0, 2),
            "critical_passed": crit_pass,
            "critical_pct": round(crit_pass / denom * 100.0, 2),
            "model_synthesis_turns": model_led_turns,
            "fallback_turns": fallback_turns,
            "deterministic_turns": deterministic_turns,
            "total_provider_calls": total_provider_calls,
            "total_tokens": total_tokens,
            "total_estimated_cost_usd": None if unpriced_calls else round(total_cost_usd, 6),
            "known_estimated_cost_usd": round(total_cost_usd, 6),
            "unpriced_requests": unpriced_calls,
            "first_response_p50_ms": p50,
            "first_response_p95_ms": p95,
            "deterministic_probe_p50_ms": warm_p50,
            "deterministic_probe_p95_ms": warm_p95,
            "model_plan_executed_turns": sum(r["model_plan_executed"] for r in turn_results),
            "selected_tool_executed_turns": sum(r["model_selected_tool_executed"] for r in turn_results),
            "expected_model_plan_turns": sum(r["expected_model_plan"] for r in turn_results),
            "correct_model_plan_turns": sum(
                r["expected_model_plan"] and r["model_plan_executed"] and r["semantic_passed"]
                for r in turn_results
            ),
            "thinking_level": thinking_level if mode == "live" else None,
            "session_id": session_id,
            "by_family": by_family,
            "failures": [r for r in turn_results if not r["semantic_passed"] or not r["critical_passed"]],
            "turns": turn_results,
        }
    finally:
        DatabaseRecordSource.get_all = orig_get_all
        DashboardRecordService.list_records = orig_list_records
        DashboardRecordService.list_analysis_records = orig_list_analysis
        DashboardRecordService.list_record_index = orig_list_index
        pe_mod._default_engine = orig_engine_default
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _failure_area(check: str, *, access_case: bool = False) -> str:
    if check.startswith(("authorization:", "critical_auth_")) or (
        access_case and check.startswith("critical_forbidden_leak:")
    ):
        return "Access control"
    if check.startswith("runtime:"):
        return "Runtime error"
    if check.startswith(("missing successful analytical tool", "routing:")):
        return "Tool selection"
    if check.startswith(("format:", "missing any of", "forbidden token")):
        return "Answer format or coverage"
    if check.startswith(("critical_fact_", "critical_number_", "critical_forbidden_leak:")):
        return "Published values and units"
    if check.startswith(("identity:", "critical_rank_")):
        return "Entity and ranking"
    if check.startswith("proposal:"):
        return "Corrective-action proposal"
    if check.startswith("critical_"):
        return "Scope and conversation context"
    if check.startswith(("idempotent_", "unexpected outcome", "expected unavailable")):
        return "Resilience and missing data"
    return "Intent and outcome"


def render_qa_summary(suites: dict[str, dict[str, Any]]) -> str:
    def inline(value: Any) -> str:
        return " ".join(str(value).split()).replace("|", r"\|")

    lines = [
        "# PMS AI conversation QA",
        "",
        "Synthetic PMS data. The first answer to each question is scored against the frozen expectations.",
        "",
        "| Suite | Mode | Passed | Turns passing critical checks | Model synthesis | p95 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    issue_groups: dict[str, dict[str, list[tuple[str, dict[str, Any], list[str]]]]] = {}
    for suite, report in suites.items():
        for mode, run in report["runs"].items():
            total = run["denominator"]
            lines.append(
                f"| {suite} | {mode} | {run['semantic_passed']}/{total} | {run['critical_passed']}/{total} | "
                f"{run['model_synthesis_turns']} | {run['first_response_p95_ms']} ms |"
            )
            for failure in run["failures"]:
                failure_details: dict[str, list[str]] = {}
                for check in [*failure["critical_failures"], *failure["semantic_failures"]]:
                    area = _failure_area(check, access_case=bool(failure["expectations"].get("critical_auth")))
                    failure_details.setdefault(area, []).append(check)
                for area, checks in failure_details.items():
                    issue_groups.setdefault(area, {}).setdefault(f"{suite}/{failure['id']}", []).append(
                        (mode, failure, checks)
                    )
    if not issue_groups:
        return "\n".join([*lines, "", "No failed turns.", ""])

    lines.extend([
        "", "## What to investigate", "",
        "For multi-turn journeys, start with the earliest failed turn. Later answers may inherit its mistake.",
        "",
    ])
    ordered = sorted(
        issue_groups, key=lambda area: (area not in {"Access control", "Runtime error"}, -len(issue_groups[area]), area)
    )
    for area in ordered:
        lines.append(f"- **{area}** — {len(issue_groups[area])} distinct failed turns")
    for area in ordered:
        lines.extend(["", f"## {area}", ""])
        for case_key, observations in issue_groups[area].items():
            first = observations[0][1]
            lines.append(f"- **{case_key} · {first['session']}** — {inline(first['prompt'])}")
            for mode, failure, checks in observations:
                lines.append(f"  - **{mode}** — {inline(failure['headline'])}")
                lines.append(f"    - {inline(' / '.join(checks))}")
                scope = ", ".join(f"{key}={value}" for key, value in failure["scope"].items() if value is not None)
                tools = ", ".join(failure["tool_calls"]) or "none"
                lines.append(f"    - Observed scope {inline(scope or 'none')} · Tools {inline(tools)}")
    return "\n".join([*lines, ""])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", nargs="+", default=["baseline", "mocked"], choices=["baseline", "mocked", "live"])
    parser.add_argument("--provider", choices=("nvidia", "cloudflare", "split"), default="nvidia")
    parser.add_argument("--nvidia-model", default="nvidia/nemotron-3.5-super-vl-120b-a12b")
    parser.add_argument("--pacing-ms", type=int, default=0)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--fixture", type=Path, help="Run a custom frozen fixture")
    group.add_argument("--suite", choices=["holdout", "conversation", "exact", "all"])
    parser.add_argument("--session", help="Rerun a single frozen session with its original turn order")
    parser.add_argument("--thinking-level", type=str.lower, choices=["none", "low", "high"])
    parser.add_argument("--out", type=Path, default=BACKEND_DIR / "scripts" / "phase6_independent_eval_report.json")
    parser.add_argument("--markdown", type=Path, help="Write a prioritized QA report")
    parser.add_argument("--fail-on-issues", action="store_true", help="Exit 1 if any scored turn fails")
    args = parser.parse_args()

    if args.session and args.suite == "all":
        parser.error("--session requires a single suite")
    available = {
        "holdout": FIXTURE_PATH,
        "conversation": CONVERSATION_FIXTURE,
        "exact": EXACT_PARAPHRASES_FIXTURE,
    }
    selected = args.suite or "holdout"
    fixtures = {"custom": args.fixture} if args.fixture else (
        available if selected == "all" else {selected: available[selected]}
    )
    protected = {
        path.resolve() for fixture in [*available.values(), *fixtures.values()]
        for path in (fixture, fixture.with_suffix(".manifest.json"))
    }
    paths = [path.resolve() for path in (args.out, args.markdown) if path is not None]
    if set(paths) & protected or len(set(paths)) != len(paths):
        parser.error("Report paths must be different and must not overwrite fixtures or manifests")

    suites: dict[str, Any] = {}
    for suite, fixture in fixtures.items():
        _, manifest = load_frozen_fixture(fixture)
        print(f"Frozen suite {suite}: {manifest['turn_count']} turns, SHA-256={manifest['fixture_sha256'][:16]}...")
        report: dict[str, Any] = {"manifest": manifest, "runs": {}}
        suites[suite] = report
        for mode in args.modes:
            run = run_eval_mode(
                mode, fixture_path=fixture, provider=args.provider, nvidia_model=args.nvidia_model,
                pacing_ms=args.pacing_ms, thinking_level=args.thinking_level, session_id=args.session,
            )
            report["runs"][mode] = run
            print(
                f"[{suite}/{mode}] {run['semantic_passed']}/{run['denominator']} passed | "
                f"{run['critical_passed']}/{run['denominator']} critical | "
                f"{run['model_synthesis_turns']} model synthesis | p95 {run['first_response_p95_ms']} ms"
            )
            for failure in run["failures"]:
                print(f"   FAIL {failure['id']} ({failure['family']}): "
                      f"{'; '.join(failure['critical_failures'] + failure['semantic_failures'])}")

    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"suites": suites} if selected == "all" else next(iter(suites.values()))
    paths[0].write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    if args.markdown:
        paths[1].write_text(render_qa_summary(suites), encoding="utf-8")
    print(f"Reports saved to {', '.join(map(str, paths))}")
    if args.fail_on_issues and any(run["failures"] for suite in suites.values() for run in suite["runs"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
