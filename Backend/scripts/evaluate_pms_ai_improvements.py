from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure Backend/ is on sys.path when executed as `python scripts/evaluate_pms_ai_improvements.py`
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.database import Base
from models.ai_schemas import AiApprovePatternRequest, AiChatRequest, AiChatResponsePayload, SessionFilterContext
from models.models import AiInteractionTrace, ProductSetting
from models.schemas import CallsData, EvaluationData, GeoBreakdown, GeoData, PerformanceRecord
from services.ai.approved_patterns import ApprovedPatternMatcher
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator
from services.dashboard_record_service import DashboardRecordService


def _cc_record(
    emp_id: str,
    name: str,
    team: str,
    month: str,
    score: float,
    *,
    position: str = "Call Center Agent",
    region: str = "EGY",
    dubai_bookings: int = 100,
    dubai_attended: int = 75,
    sharjah_bookings: int = 40,
    sharjah_attended: int = 30,
    ajman_bookings: int = 20,
    ajman_attended: int = 14,
    booking_rate: float = 0.30,
    reachability: float = 0.88,
    abandon_rate: float = 0.04,
) -> PerformanceRecord:
    total_bookings = dubai_bookings + sharjah_bookings + ajman_bookings + 10
    total_attended = dubai_attended + sharjah_attended + ajman_attended + 8
    attend_rate = (total_attended / total_bookings) if total_bookings > 0 else 0.0
    other_label = "Abandon Rate" if team == "Inbound" else "Reachability"
    other_val = abandon_rate if team == "Inbound" else reachability
    other_target = 0.05 if team == "Inbound" else 0.90

    return PerformanceRecord(
        id=f"{team}_{emp_id}_2026_{month[:3]}",
        employee_id=emp_id,
        employee_name=name,
        team=team,
        month=month,
        year=2026,
        region=region,
        position=position,
        performance_level="Employee",
        status="Below Target" if score < 80 else "On Track",
        evaluation=EvaluationData(score=score, grade="C" if score < 80 else ("A" if score >= 90 else "B")),
        calls=CallsData(inbound=400, total_handled=500, abandoned=int(400 * abandon_rate)),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=dubai_bookings, sharjah=sharjah_bookings, ajman=ajman_bookings, clinics=10),
            attended=GeoBreakdown(dubai=dubai_attended, sharjah=sharjah_attended, ajman=ajman_attended, clinics=8),
        ),
        kpi_values=[
            {
                "kpi_key": "Attendance",
                "label": "Attendance Rate",
                "actual_value": round(attend_rate, 4),
                "target_value": 0.65,
                "weight_applied": 0.70,
                "contribution": round(min(attend_rate / 0.65, 1.0) * 0.70, 4),
            },
            {
                "kpi_key": "Booking",
                "label": "Booking Rate",
                "actual_value": booking_rate,
                "target_value": 0.30,
                "weight_applied": 0.10,
                "contribution": round((booking_rate / 0.30) * 0.10, 4),
            },
            {
                "kpi_key": "Other",
                "label": other_label,
                "actual_value": other_val,
                "target_value": other_target,
                "weight_applied": 0.10,
                "contribution": 0.08,
            },
        ],
    )


def _support_record(
    emp_id: str,
    name: str,
    position: str,
    month: str,
    score: float,
    kpi_key: str,
    kpi_label: str,
    actual: float,
    target: float,
) -> PerformanceRecord:
    return PerformanceRecord(
        id=f"SUP_{emp_id}_2026_{month[:3]}",
        employee_id=emp_id,
        employee_name=name,
        team="Call Center",
        month=month,
        year=2026,
        region="EGY",
        position=position,
        performance_level="Employee",
        status="Below Target" if score < 80 else "On Track",
        evaluation=EvaluationData(score=score, grade="B" if score >= 80 else "C"),
        calls=CallsData(inbound=0, total_handled=0, abandoned=0),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=0, sharjah=0, ajman=0, clinics=0),
            attended=GeoBreakdown(dubai=0, sharjah=0, ajman=0, clinics=0),
        ),
        kpi_values=[
            {
                "kpi_key": kpi_key,
                "label": kpi_label,
                "actual_value": actual,
                "target_value": target,
                "achievement_ratio": round(actual / target, 4) if target else 1.0,
                "weight_applied": 0.60,
                "unit": "%",
                "direction": "higher_better",
            }
        ],
    )


def _rcm_record(
    emp_id: str,
    name: str,
    team: str,
    region: str,
    month: str,
    score: float,
    position: str,
    kpi_label: str,
    actual: float,
    target: float,
) -> PerformanceRecord:
    return PerformanceRecord(
        id=f"{team}_{emp_id}_2026_{month[:3]}",
        employee_id=emp_id,
        employee_name=name,
        team=team,
        month=month,
        year=2026,
        region=region,
        position=position,
        performance_level="Employee",
        status="Below Target" if score < 80 else "On Track",
        evaluation=EvaluationData(score=score, grade="B" if score >= 80 else "C"),
        calls=CallsData(inbound=0, total_handled=0, abandoned=0),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=0, sharjah=0, ajman=0, clinics=0),
            attended=GeoBreakdown(dubai=0, sharjah=0, ajman=0, clinics=0),
        ),
        kpi_values=[
            {
                "kpi_key": "Accuracy",
                "label": kpi_label,
                "actual_value": actual,
                "target_value": target,
                "achievement_ratio": round(actual / target, 4) if target else 1.0,
                "weight_applied": 0.60,
                "unit": "%",
                "direction": "higher_better",
            }
        ],
    )


def build_synthetic_dataset() -> list[PerformanceRecord]:
    records: list[PerformanceRecord] = []

    # Inbound Call Center (July -> August drop -> September recovery)
    inbound_specs = [
        # (emp_id, name, pos, month, score, d_bk, d_att, s_bk, s_att, a_bk, a_att, bk_rate, aband)
        ("EMP101", "Sara Mahmoud", "Senior Inbound Agent", "July", 92.0, 210, 175, 55, 44, 25, 20, 0.34, 0.03),
        ("EMP102", "Radwa Ahmed", "Inbound Agent", "July", 86.0, 160, 128, 45, 34, 20, 15, 0.29, 0.04),
        ("EMP103", "Youssef Adel", "Inbound Agent", "July", 82.0, 130, 100, 35, 26, 18, 12, 0.27, 0.05),

        ("EMP101", "Sara Mahmoud", "Senior Inbound Agent", "August", 84.0, 180, 125, 50, 33, 22, 15, 0.30, 0.05),
        ("EMP102", "Radwa Ahmed", "Inbound Agent", "August", 76.0, 140, 82, 40, 23, 18, 10, 0.24, 0.07),
        ("EMP103", "Youssef Adel", "Inbound Agent", "August", 72.0, 120, 66, 32, 17, 15, 8, 0.22, 0.08),

        ("EMP101", "Sara Mahmoud", "Senior Inbound Agent", "September", 94.5, 235, 198, 62, 51, 28, 22, 0.36, 0.025),
        ("EMP102", "Radwa Ahmed", "Inbound Agent", "September", 87.5, 180, 142, 48, 38, 24, 19, 0.31, 0.04),
        ("EMP103", "Youssef Adel", "Inbound Agent", "September", 83.0, 145, 112, 42, 32, 20, 15, 0.28, 0.045),
    ]
    for emp_id, name, pos, mo, sc, db, da, sb, sa, ab, aa, br, ab_r in inbound_specs:
        records.append(
            _cc_record(
                emp_id, name, "Inbound", mo, sc,
                position=pos, region="EGY",
                dubai_bookings=db, dubai_attended=da,
                sharjah_bookings=sb, sharjah_attended=sa,
                ajman_bookings=ab, ajman_attended=aa,
                booking_rate=br, abandon_rate=ab_r,
            )
        )

    # Inbound UAE (to verify country switching)
    for mo, sc, db, da, sb, sa in [
        ("August", 81.0, 95, 72, 35, 25),
        ("September", 89.0, 120, 98, 44, 35),
    ]:
        records.append(
            _cc_record(
                "EMP151", "Mariam Al Suwaidi", "UAE Inbound Specialist", mo, sc,
                position="UAE Inbound Specialist", region="UAE",
                dubai_bookings=db, dubai_attended=da,
                sharjah_bookings=sb, sharjah_attended=sa,
                ajman_bookings=22, ajman_attended=16,
                booking_rate=0.33, abandon_rate=0.035,
            )
        )

    # Outbound Call Center
    outbound_specs = [
        ("EMP201", "Omar Khaled", "Outbound Agent", "July", 84.0, 110, 82, 42, 30, 0.87),
        ("EMP202", "Hana Mostafa", "Senior Outbound Agent", "July", 89.0, 140, 110, 50, 40, 0.91),
        ("EMP201", "Omar Khaled", "Outbound Agent", "August", 77.5, 95, 65, 38, 24, 0.81),
        ("EMP202", "Hana Mostafa", "Senior Outbound Agent", "August", 85.0, 125, 95, 45, 34, 0.88),
        ("EMP201", "Omar Khaled", "Outbound Agent", "September", 83.5, 115, 86, 48, 36, 0.86),
        ("EMP202", "Hana Mostafa", "Senior Outbound Agent", "September", 91.0, 155, 126, 65, 54, 0.93),
    ]
    for emp_id, name, pos, mo, sc, db, da, sb, sa, reach in outbound_specs:
        records.append(
            _cc_record(
                emp_id, name, "Outbound", mo, sc,
                position=pos, region="EGY",
                dubai_bookings=db, dubai_attended=da,
                sharjah_bookings=sb, sharjah_attended=sa,
                ajman_bookings=18, ajman_attended=14,
                booking_rate=0.29, reachability=reach,
            )
        )

    # Support Positions (Quality Assurance, Call Center trainer, Workforce analyst)
    for mo, qa_s, tr_s, wf_s in [
        ("July", 88.0, 86.0, 90.0),
        ("August", 85.0, 84.0, 88.5),
        ("September", 91.0, 89.5, 93.0),
    ]:
        records.append(_support_record("EMP301", "Dina Samir", "Quality Assurance", mo, qa_s, "QAAuditScore", "QA Audit Score", qa_s / 100.0, 0.90))
        records.append(_support_record("EMP302", "Karim Nabil", "Call Center trainer", mo, tr_s, "TrainingPassRate", "Training Pass Rate", tr_s / 100.0, 0.88))
        records.append(_support_record("EMP303", "Nour Hassan", "Workforce analyst", mo, wf_s, "ForecastAccuracy", "Forecast Accuracy", wf_s / 100.0, 0.90))

    # RCM Egypt vs RCM UAE
    for mo, c_egy, c_uae, s_egy, s_uae, r_egy, r_uae in [
        ("July", 87.0, 90.0, 85.0, 88.0, 82.0, 86.0),
        ("August", 84.0, 88.5, 82.5, 86.0, 79.0, 84.0),
        ("September", 91.5, 93.0, 89.0, 91.0, 85.5, 89.0),
    ]:
        records.append(_rcm_record("EMP401", "Mina George", "Coding EGY", "EGY", mo, c_egy, "Medical Coder", "Coding Accuracy", c_egy / 100.0, 0.92))
        records.append(_rcm_record("EMP402", "Fatima Ali", "Coding", "UAE", mo, c_uae, "UAE Medical Coder", "Coding Accuracy", c_uae / 100.0, 0.92))
        records.append(_rcm_record("EMP403", "Tarek Mansour", "Submission EGY", "EGY", mo, s_egy, "Submission Specialist", "Submission Accuracy", s_egy / 100.0, 0.90))
        records.append(_rcm_record("EMP404", "Layla Rashid", "Submission", "UAE", mo, s_uae, "UAE Submission Specialist", "Submission Accuracy", s_uae / 100.0, 0.90))
        records.append(_rcm_record("EMP405", "Salma Fathy", "Resubmission", "EGY", mo, r_egy, "Resubmission Specialist", "Recovery Rate", r_egy / 100.0, 0.85))
        records.append(_rcm_record("EMP406", "Noora Zayed", "Re-Submission", "UAE", mo, r_uae, "UAE Resubmission Specialist", "Recovery Rate", r_uae / 100.0, 0.85))

    return records


@dataclass
class EvalCase:
    case_id: str
    suite: str
    chain_id: str
    turn_number: int
    prompt: str
    initial_state: SessionFilterContext
    is_followup: bool
    check_intent: Callable[[AiChatResponsePayload], tuple[bool, str]]
    check_followup: Callable[[AiChatResponsePayload], tuple[bool, str]] | None
    check_answer: Callable[[AiChatResponsePayload], tuple[bool, str]]


def _intent_eq(resp: AiChatResponsePayload, expected_outcome: str, *expected_intents: str) -> tuple[bool, str]:
    if resp.outcome != expected_outcome:
        return False, f"outcome={resp.outcome!r} != {expected_outcome!r}"
    if expected_intents:
        actual = resp.structured_query.intent if resp.structured_query else None
        if actual not in expected_intents:
            return False, f"intent={actual!r} not in {expected_intents!r}"
    return True, "ok"


def _clar_eq(resp: AiChatResponsePayload, code: str) -> tuple[bool, str]:
    if resp.outcome != "clarification":
        return False, f"outcome={resp.outcome!r} != 'clarification'"
    actual_code = resp.structured_query.clarification_code if resp.structured_query else None
    if actual_code != code:
        return False, f"clarification_code={actual_code!r} != {code!r}"
    return True, "ok"


def _contains_any(text: str, *needles: str) -> bool:
    low = text.casefold()
    return any(n.casefold() in low for n in needles)


def _full_text(resp: AiChatResponsePayload) -> str:
    parts = [resp.headline or "", *resp.narrative_bullets, resp.scope_banner or ""]
    return "\n".join(parts)


def build_eval_cases() -> list[EvalCase]:
    cc_state = SessionFilterContext(function="Call Center")
    rcm_state = SessionFilterContext(function="RCM")

    cases: list[EvalCase] = [
        # ---------------- SUITE A: Multi-turn Follow-up Chains ----------------
        # Chain A1: Bookings leader -> What about September? -> And Dubai?
        EvalCase(
            "A01_chain1_turn1", "suite_a", "chain_a1", 1,
            "Bookings leader",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "ranking", "current_value"),
            None,
            lambda r: (
                "Sara Mahmoud" in _full_text(r) and _contains_any(_full_text(r), "booking", "bookings"),
                f"headline={r.headline!r}",
            ),
        ),
        EvalCase(
            "A02_chain1_turn2", "suite_a", "chain_a1", 2,
            "What about September?",
            cc_state, True,
            lambda r: _intent_eq(r, "answer", "ranking", "current_value"),
            lambda r: (
                bool(r.structured_query and r.structured_query.periods == ["2026-09"])
                and bool(r.structured_query and (r.structured_query.metric or "").endswith("bookings_count")),
                f"sq={r.structured_query.model_dump() if r.structured_query else None}",
            ),
            lambda r: (
                "September 2026" in _full_text(r) and "Sara Mahmoud" in _full_text(r),
                f"headline={r.headline!r}",
            ),
        ),
        EvalCase(
            "A03_chain1_turn3", "suite_a", "chain_a1", 3,
            "And Dubai?",
            cc_state, True,
            lambda r: _intent_eq(r, "answer", "ranking", "current_value"),
            lambda r: (
                bool(r.structured_query and r.structured_query.branch == "dubai")
                and bool(r.structured_query and r.structured_query.periods == ["2026-09"]),
                f"sq={r.structured_query.model_dump() if r.structured_query else None}",
            ),
            lambda r: (
                "Dubai" in _full_text(r) and "September 2026" in _full_text(r) and "Sara Mahmoud" in _full_text(r),
                f"headline={r.headline!r}",
            ),
        ),

        # Chain A2: Who is leading Inbound bookings? -> What about UAE? (country switch)
        EvalCase(
            "A04_chain2_turn1", "suite_a", "chain_a2", 1,
            "Who is leading Inbound bookings?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "ranking", "current_value"),
            None,
            lambda r: (
                "Inbound" in _full_text(r) and _contains_any(_full_text(r), "Sara Mahmoud", "Mariam Al Suwaidi"),
                f"headline={r.headline!r}",
            ),
        ),
        EvalCase(
            "A05_chain2_turn2", "suite_a", "chain_a2", 2,
            "What about UAE?",
            cc_state, True,
            lambda r: _intent_eq(r, "answer", "ranking", "current_value", "actual_vs_target"),
            lambda r: (
                bool(r.resolved_session_state and (r.resolved_session_state.region == "UAE" or (r.resolved_session_state.last_confirmed_query and r.resolved_session_state.last_confirmed_query.region == "UAE")))
                and bool(r.structured_query and r.structured_query.team == "Inbound"),
                f"res={r.resolved_session_state.model_dump()}",
            ),
            lambda r: (
                _contains_any(_full_text(r), "UAE", "Mariam Al Suwaidi"),
                f"headline={r.headline!r}",
            ),
        ),

        # Chain A3: What is Inbound score in August? -> Why did it drop?
        EvalCase(
            "A06_chain3_turn1", "suite_a", "chain_a3", 1,
            "What is Inbound score in August?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: (
                "Inbound" in _full_text(r) and "August" in _full_text(r),
                f"headline={r.headline!r}",
            ),
        ),
        EvalCase(
            "A07_chain3_turn2", "suite_a", "chain_a3", 2,
            "Why did it drop?",
            cc_state, True,
            lambda r: _intent_eq(r, "answer", "score_drivers", "actual_vs_target", "compare_periods"),
            lambda r: (
                bool(r.structured_query and r.structured_query.team == "Inbound")
                and bool(r.structured_query and r.structured_query.periods == ["2026-08"]),
                f"sq={r.structured_query.model_dump() if r.structured_query else None}",
            ),
            lambda r: (
                "Inbound" in _full_text(r)
                and _contains_any(_full_text(r), "contributor", "drivers", "attendance", "below target", "gap", "drag"),
                f"headline={r.headline!r}",
            ),
        ),

        # Chain A4: Who is the top agent in Inbound in September? -> What about his position? (single unambiguous person)
        EvalCase(
            "A08_chain4_turn1", "suite_a", "chain_a4", 1,
            "Who is the top agent in Inbound in September?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "ranking"),
            None,
            lambda r: (
                "Sara Mahmoud" in _full_text(r) and "September" in _full_text(r),
                f"headline={r.headline!r}",
            ),
        ),
        EvalCase(
            "A09_chain4_turn2", "suite_a", "chain_a4", 2,
            "What about his position?",
            cc_state, True,
            lambda r: _intent_eq(r, "answer", "ranking", "current_value", "scorecard_structure", "actual_vs_target"),
            lambda r: (
                bool(r.resolved_session_state and r.resolved_session_state.last_confirmed_query and r.resolved_session_state.last_confirmed_query.last_subject_employee_name == "Sara Mahmoud")
                or "Sara Mahmoud" in _full_text(r),
                f"headline={r.headline!r}",
            ),
            lambda r: (
                "Sara Mahmoud" in _full_text(r) and "Senior Inbound Agent" in _full_text(r),
                f"text={_full_text(r)!r}",
            ),
        ),

        # Chain A5: Show top 3 agents in Inbound in September -> What about his position? (must clarify ambiguous person!)
        EvalCase(
            "A10_chain5_turn1", "suite_a", "chain_a5", 1,
            "Show top 3 agents in Inbound in September",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "ranking"),
            None,
            lambda r: (
                "Sara Mahmoud" in _full_text(r) and "Radwa Ahmed" in _full_text(r),
                f"headline={r.headline!r}",
            ),
        ),
        EvalCase(
            "A11_chain5_turn2", "suite_a", "chain_a5", 2,
            "What about his position?",
            cc_state, True,
            lambda r: _clar_eq(r, "AMBIGUOUS_PERSON"),
            lambda r: (
                r.outcome == "clarification" and r.clarification is not None and r.clarification.code == "AMBIGUOUS_PERSON",
                f"outcome={r.outcome!r}, clar={r.clarification.code if r.clarification else None}",
            ),
            lambda r: (
                r.outcome == "clarification" and bool(r.clarification and len(r.clarification.choices) >= 2),
                f"choices={len(r.clarification.choices) if r.clarification else 0}",
            ),
        ),

        # ---------------- SUITE A: Varied Phrasings & Core Cases (15 more -> 26 total) ----------------
        EvalCase(
            "A12_bookings_leader_v1", "suite_a", "a12", 1,
            "Who leads bookings in September 2026?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "ranking"),
            None,
            lambda r: ("Sara Mahmoud" in _full_text(r) and _contains_any(_full_text(r), "booking"), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A13_bookings_leader_v2", "suite_a", "a13", 1,
            "Which agent generated the most bookings in September?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "ranking"),
            None,
            lambda r: ("Sara Mahmoud" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A14_bookings_leader_v3", "suite_a", "a14", 1,
            "Top bookings performer in Inbound for August 2026",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "ranking"),
            None,
            lambda r: ("Sara Mahmoud" in _full_text(r) and "August 2026" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A15_team_score_v1", "suite_a", "a15", 1,
            "How is Inbound doing in September 2026?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Inbound" in _full_text(r) and "September 2026" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A16_team_score_v2", "suite_a", "a16", 1,
            "What is the Outbound overall score in August 2026?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Outbound" in _full_text(r) and "August 2026" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A17_team_score_v3", "suite_a", "a17", 1,
            "Give me Inbound performance summary for July 2026",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Inbound" in _full_text(r) and "July 2026" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A18_kpi_gap_v1", "suite_a", "a18", 1,
            "What is dragging Inbound attendance down in August 2026?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "score_drivers", "actual_vs_target"),
            None,
            lambda r: ("Inbound" in _full_text(r) and "Attendance" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A19_kpi_gap_v2", "suite_a", "a19", 1,
            "Outbound reachability vs target in September 2026",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Outbound" in _full_text(r) and "Reachability" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A20_kpi_gap_v3", "suite_a", "a20", 1,
            "Where is Inbound missing target in August 2026?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "score_drivers", "actual_vs_target"),
            None,
            lambda r: ("Inbound" in _full_text(r) and "August 2026" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A21_support_workforce", "suite_a", "a21", 1,
            "How is Workforce analyst performing in Support Positions in September 2026?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Workforce analyst" in _full_text(r) and "Support Positions" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A22_support_qa", "suite_a", "a22", 1,
            "Quality Assurance scorecard in Support Positions for September 2026",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value", "scorecard_structure"),
            None,
            lambda r: ("Quality Assurance" in _full_text(r) and "Support Positions" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A23_support_trainer", "suite_a", "a23", 1,
            "Call Center trainer performance in September 2026",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Call Center trainer" in _full_text(r) and "Support Positions" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A24_branch_compare", "suite_a", "a24", 1,
            "Which has more bookings in September: Dubai, Sharjah, or Ajman?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "compare_branches", "ranking"),
            None,
            lambda r: ("Dubai" in _full_text(r) and "Sharjah" in _full_text(r) and "Ajman" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A25_rcm_coding_egy", "suite_a", "a25", 1,
            "How is Coding EGY performing in September 2026?",
            rcm_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Coding EGY" in _full_text(r) and "September 2026" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "A26_missing_november", "suite_a", "a26", 1,
            "What is Inbound score in November 2026?",
            cc_state, False,
            lambda r: _intent_eq(r, "unavailable_data"),
            None,
            lambda r: ("November 2026" in _full_text(r) and r.outcome == "unavailable_data", f"h={r.headline!r}"),
        ),

        # ---------------- SUITE B: Held-Out Generalization Set (16 cases) ----------------
        # Unseen Chain B1: Outbound reachability -> What about September? -> And Sharjah?
        EvalCase(
            "B01_chainb1_turn1", "suite_b", "chain_b1", 1,
            "Check Outbound reachability for August 2026",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Outbound" in _full_text(r) and "Reachability" in _full_text(r) and "August 2026" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "B02_chainb1_turn2", "suite_b", "chain_b1", 2,
            "What about September?",
            cc_state, True,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            lambda r: (
                bool(r.structured_query and r.structured_query.team == "Outbound")
                and bool(r.structured_query and r.structured_query.periods == ["2026-09"])
                and bool(r.structured_query and (r.structured_query.metric or "").endswith("reachability")),
                f"sq={r.structured_query.model_dump() if r.structured_query else None}",
            ),
            lambda r: ("Outbound" in _full_text(r) and "September 2026" in _full_text(r) and "Reachability" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "B03_chainb1_turn3", "suite_b", "chain_b1", 3,
            "And Sharjah?",
            cc_state, True,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            lambda r: (
                bool(r.structured_query and r.structured_query.team == "Outbound")
                and bool(r.structured_query and r.structured_query.branch == "sharjah")
                and bool(r.structured_query and r.structured_query.periods == ["2026-09"]),
                f"sq={r.structured_query.model_dump() if r.structured_query else None}",
            ),
            lambda r: ("Sharjah" in _full_text(r) and "Outbound" in _full_text(r) and "September 2026" in _full_text(r), f"h={r.headline!r}"),
        ),

        # Unseen Chain B2: RCM Egypt -> What about UAE?
        EvalCase(
            "B04_chainb2_turn1", "suite_b", "chain_b2", 1,
            "How is Submission EGY doing in September?",
            rcm_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Submission EGY" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "B05_chainb2_turn2", "suite_b", "chain_b2", 2,
            "What about UAE?",
            rcm_state, True,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            lambda r: (
                bool(r.structured_query and r.structured_query.team == "Submission"),
                f"sq={r.structured_query.model_dump() if r.structured_query else None}",
            ),
            lambda r: ("Submission" in _full_text(r) and "Submission EGY" not in (r.scope_banner or ""), f"h={r.headline!r}, sb={r.scope_banner!r}"),
        ),

        # Unseen Chain B3: Highest scoring agent -> What is the role of the top agent?
        EvalCase(
            "B06_chainb3_turn1", "suite_b", "chain_b3", 1,
            "Who achieved the highest score in Outbound in September 2026?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "ranking"),
            None,
            lambda r: ("Hana Mostafa" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "B07_chainb3_turn2", "suite_b", "chain_b3", 2,
            "What is the role of the top agent?",
            cc_state, True,
            lambda r: _intent_eq(r, "answer", "ranking", "current_value", "scorecard_structure", "actual_vs_target"),
            lambda r: (
                "Hana Mostafa" in _full_text(r) or bool(r.resolved_session_state and r.resolved_session_state.last_confirmed_query and r.resolved_session_state.last_confirmed_query.last_subject_employee_name == "Hana Mostafa"),
                f"h={r.headline!r}",
            ),
            lambda r: ("Hana Mostafa" in _full_text(r) and "Senior Outbound Agent" in _full_text(r), f"t={_full_text(r)!r}"),
        ),

        # Unseen individual phrasings
        EvalCase(
            "B08_unseen_resub_egy", "suite_b", "b08", 1,
            "Evaluate Egypt Resubmission performance for September 2026",
            rcm_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Resubmission" in _full_text(r) and "September 2026" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "B09_unseen_resub_uae", "suite_b", "b09", 1,
            "How did UAE Re-Submission perform in August 2026?",
            rcm_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Re-Submission" in _full_text(r) and "August 2026" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "B10_unseen_coding_uae", "suite_b", "b10", 1,
            "Show UAE Coding numbers in July 2026",
            rcm_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Coding" in _full_text(r) and "Coding EGY" not in (r.scope_banner or "") and "July 2026" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "B11_unseen_abandon", "suite_b", "b11", 1,
            "Did Inbound keep abandon rate within target in September 2026?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Inbound" in _full_text(r) and "Abandon Rate" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "B12_unseen_ajman_bookings", "suite_b", "b12", 1,
            "How many Inbound bookings came from Ajman in September 2026?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "current_value", "actual_vs_target"),
            None,
            lambda r: ("Ajman" in _full_text(r) and "Inbound" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "B13_unseen_outbound_trend", "suite_b", "b13", 1,
            "Display Outbound score progression from July to September 2026",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "trend", "compare_periods"),
            None,
            lambda r: ("Outbound" in _full_text(r) and _contains_any(_full_text(r), "July", "September"), f"h={r.headline!r}"),
        ),
        EvalCase(
            "B14_unseen_support_roll", "suite_b", "b14", 1,
            "Give me the Support Positions overall average in September 2026",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "actual_vs_target", "current_value"),
            None,
            lambda r: ("Support Positions" in _full_text(r) and "September 2026" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "B15_unseen_lowest_inbound", "suite_b", "b15", 1,
            "Which Inbound employee had the weakest score in August 2026?",
            cc_state, False,
            lambda r: _intent_eq(r, "answer", "ranking"),
            None,
            lambda r: ("Youssef Adel" in _full_text(r), f"h={r.headline!r}"),
        ),
        EvalCase(
            "B16_unseen_missing_nov", "suite_b", "b16", 1,
            "What were Outbound bookings in November 2026?",
            cc_state, False,
            lambda r: _intent_eq(r, "unavailable_data"),
            None,
            lambda r: ("November 2026" in _full_text(r), f"h={r.headline!r}"),
        ),
    ]
    return cases


def run_evaluation() -> dict[str, Any]:
    os.environ.setdefault("PMS_AI_ROUTER_MODE", "deterministic")
    records = build_synthetic_dataset()

    orig_list_records = DashboardRecordService.list_records
    orig_list_analysis = DashboardRecordService.list_analysis_records
    orig_list_index = DashboardRecordService.list_record_index

    DashboardRecordService.list_records = lambda _self, **_kw: records  # type: ignore[method-assign]
    DashboardRecordService.list_analysis_records = lambda _self, **_kw: records  # type: ignore[method-assign]
    DashboardRecordService.list_record_index = lambda _self: None  # type: ignore[method-assign]
    ai_evidence_cache.clear()

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    cases = build_eval_cases()
    chain_states: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    scope = {
        "role": "Admin",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "has_unrestricted_team_access": True,
    }

    try:
        with SessionLocal() as db:
            orch = PmsAiOrchestrator(db, scope)
            for case in cases:
                chain_ctx = chain_states.setdefault(
                    case.chain_id,
                    {
                        "conversation_id": str(uuid.uuid4()),
                        "context_version": 0,
                        "session_state": case.initial_state,
                    },
                )
                req = AiChatRequest(
                    prompt=case.prompt,
                    conversation_id=chain_ctx["conversation_id"],
                    context_version=chain_ctx["context_version"] or None,
                    client_request_id=f"eval-{case.case_id}",
                    session_state=chain_ctx["session_state"],
                    provider_override="deterministic",
                )
                resp = orch.run_chat_turn(req)
                chain_ctx["conversation_id"] = resp.conversation_id or chain_ctx["conversation_id"]
                chain_ctx["context_version"] = resp.context_version
                chain_ctx["session_state"] = resp.resolved_session_state

                intent_ok, intent_reason = case.check_intent(resp)
                if case.check_followup is not None:
                    followup_ok, followup_reason = case.check_followup(resp)
                else:
                    followup_ok, followup_reason = True, "n/a"
                answer_ok, answer_reason = case.check_answer(resp)

                results.append(
                    {
                        "case_id": case.case_id,
                        "suite": case.suite,
                        "chain_id": case.chain_id,
                        "turn_number": case.turn_number,
                        "is_followup": case.is_followup,
                        "prompt": case.prompt,
                        "outcome": resp.outcome,
                        "intent": resp.structured_query.intent if resp.structured_query else None,
                        "clarification_code": resp.structured_query.clarification_code if resp.structured_query else None,
                        "headline": resp.headline,
                        "intent_ok": intent_ok,
                        "intent_reason": intent_reason,
                        "followup_ok": followup_ok,
                        "followup_reason": followup_reason,
                        "answer_ok": answer_ok,
                        "answer_reason": answer_reason,
                    }
                )
    finally:
        DashboardRecordService.list_records = orig_list_records  # type: ignore[method-assign]
        DashboardRecordService.list_analysis_records = orig_list_analysis  # type: ignore[method-assign]
        DashboardRecordService.list_record_index = orig_list_index  # type: ignore[method-assign]

    def _summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(items)
        followups = [x for x in items if x["is_followup"]]
        intent_acc = round(sum(1 for x in items if x["intent_ok"]) / total, 4) if total else 0.0
        followup_acc = (
            round(sum(1 for x in followups if x["followup_ok"]) / len(followups), 4)
            if followups
            else 1.0
        )
        answer_acc = round(sum(1 for x in items if x["answer_ok"]) / total, 4) if total else 0.0
        return {
            "total_cases": total,
            "followup_cases": len(followups),
            "intent_accuracy": intent_acc,
            "followup_context_accuracy": followup_acc,
            "answer_accuracy": answer_acc,
            "intent_passed": sum(1 for x in items if x["intent_ok"]),
            "followup_passed": sum(1 for x in followups if x["followup_ok"]),
            "answer_passed": sum(1 for x in items if x["answer_ok"]),
        }

    suite_a_items = [x for x in results if x["suite"] == "suite_a"]
    suite_b_items = [x for x in results if x["suite"] == "suite_b"]
    pattern_learning = run_pattern_learning_evaluation(records)

    report = {
        "suites": {
            "suite_a": _summarize(suite_a_items),
            "suite_b": _summarize(suite_b_items),
            "overall": _summarize(results),
        },
        "pattern_learning": pattern_learning,
        "cases": results,
    }
    return report


def run_pattern_learning_evaluation(records: list[PerformanceRecord]) -> dict[str, Any]:
    """Compare BEFORE (no approved patterns) vs AFTER (Admin-verified patterns) on messy & unseen paraphrases."""
    orig_list_records = DashboardRecordService.list_records
    orig_list_analysis = DashboardRecordService.list_analysis_records
    orig_list_index = DashboardRecordService.list_record_index

    DashboardRecordService.list_records = lambda _self, **_kw: records  # type: ignore[method-assign]
    DashboardRecordService.list_analysis_records = lambda _self, **_kw: records  # type: ignore[method-assign]
    DashboardRecordService.list_record_index = lambda _self: None  # type: ignore[method-assign]
    ai_evidence_cache.clear()

    training_specs = [
        {
            "case_id": "PL-TRN-01",
            "prompt": "Please list the Inbound mvp badge in September 2026",
            "session": SessionFilterContext(team="Inbound", month="September", year=2026),
            "intent": "ranking",
            "operation_kind": "ranking",
            "requested_parts": ["ranking"],
            "tool_choice": "get_team_rankings",
        },
        {
            "case_id": "PL-TRN-02",
            "prompt": "Inbound rubric blueprint check in September 2026",
            "session": SessionFilterContext(team="Inbound", month="September", year=2026),
            "intent": "scorecard_structure",
            "operation_kind": "scorecard_structure",
            "requested_parts": ["scorecard_structure"],
            "tool_choice": "get_scorecard_structure",
        },
        {
            "case_id": "PL-TRN-03",
            "prompt": "Inbound headache points in August 2026",
            "session": SessionFilterContext(team="Inbound", month="August", year=2026),
            "intent": "score_drivers",
            "operation_kind": "score_drivers",
            "requested_parts": ["drivers"],
            "tool_choice": "get_score_drivers",
        },
        {
            "case_id": "PL-TRN-04",
            "prompt": "Inbound paired with Outbound duel check in September 2026",
            "session": SessionFilterContext(month="September", year=2026),
            "intent": "compare_teams",
            "operation_kind": "compare_teams",
            "requested_parts": ["compare_teams"],
            "tool_choice": "compare_teams",
        },
        {
            "case_id": "PL-TRN-05",
            "prompt": "Inbound streak arc check",
            "session": SessionFilterContext(team="Inbound", month="September", year=2026),
            "intent": "trend",
            "operation_kind": "trend",
            "requested_parts": ["trend"],
            "tool_choice": "get_team_trend",
        },
    ]

    unseen_specs = [
        {
            "case_id": "PL-UNSEEN-01",
            "prompt": "Show me the Outbound mvp badge in August 2026",
            "session": SessionFilterContext(month="August", year=2026),
            "expected_intent": "ranking",
            "expected_text_any": ("Outbound", "August 2026"),
        },
        {
            "case_id": "PL-UNSEEN-02",
            "prompt": "Show Outbound rubric blueprint check in August 2026",
            "session": SessionFilterContext(month="August", year=2026),
            "expected_intent": "scorecard_structure",
            "expected_text_any": ("Outbound", "KPI", "weight"),
        },
        {
            "case_id": "PL-UNSEEN-03",
            "prompt": "Show Outbound headache points in September 2026",
            "session": SessionFilterContext(month="September", year=2026),
            "expected_intent": "score_drivers",
            "expected_text_any": ("Outbound", "September 2026"),
        },
        {
            "case_id": "PL-UNSEEN-04",
            "prompt": "Show RCM with Inbound duel check in August 2026",
            "session": SessionFilterContext(month="August", year=2026),
            "expected_intent": "compare_teams",
            "expected_text_any": ("RCM", "Inbound"),
        },
        {
            "case_id": "PL-UNSEEN-05",
            "prompt": "Show Outbound streak arc check",
            "session": SessionFilterContext(month="September", year=2026),
            "expected_intent": "trend",
            "expected_text_any": ("Outbound", "trend", "month", "July", "August", "September"),
        },
    ]

    scope = {
        "role": "Admin",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "has_unrestricted_team_access": True,
    }

    def _run_on_db(seed_patterns: bool) -> dict[str, Any]:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)
        with SessionLocal() as db:
            db.add(ProductSetting(key="ai_enabled", enabled=True))
            db.commit()
            orch = PmsAiOrchestrator(db, scope)

            if seed_patterns:
                matcher = ApprovedPatternMatcher(db)
                for spec in training_specs:
                    resp = orch.run_chat_turn(
                        AiChatRequest(
                            prompt=spec["prompt"],
                            session_state=spec["session"],
                            provider_override="deterministic",
                        )
                    )
                    assert resp.trace_id
                    matcher.approve_pattern_from_trace(
                        trace_id=resp.trace_id,
                        payload=AiApprovePatternRequest(
                            corrected_pattern_prompt=spec["prompt"],
                            intent=spec["intent"],
                            operation_kind=spec["operation_kind"],
                            requested_parts=spec["requested_parts"],
                            tool_choice=spec["tool_choice"],
                            failure_category="misunderstood_question",
                            verified_against_pms=True,
                            review_notes="Eval benchmark verified pattern",
                        ),
                        approver_user_id="00000000-0000-0000-0000-000000000001",
                        caller_role="Admin",
                    )

            ai_evidence_cache.clear()
            train_results: list[dict[str, Any]] = []
            for spec in training_specs:
                r = orch.run_chat_turn(
                    AiChatRequest(
                        prompt=spec["prompt"],
                        session_state=spec["session"],
                        provider_override="deterministic",
                    )
                )
                actual_intent = r.structured_query.intent if r.structured_query else None
                intent_ok = r.outcome == "answer" and actual_intent == spec["intent"]
                train_results.append(
                    {
                        "case_id": spec["case_id"],
                        "prompt": spec["prompt"],
                        "expected_intent": spec["intent"],
                        "actual_intent": actual_intent,
                        "outcome": r.outcome,
                        "intent_ok": intent_ok,
                    }
                )

            unseen_results: list[dict[str, Any]] = []
            for spec in unseen_specs:
                r = orch.run_chat_turn(
                    AiChatRequest(
                        prompt=spec["prompt"],
                        session_state=spec["session"],
                        provider_override="deterministic",
                    )
                )
                actual_intent = r.structured_query.intent if r.structured_query else None
                intent_ok = r.outcome == "answer" and actual_intent == spec["expected_intent"]
                text = _full_text(r)
                answer_ok = intent_ok and _contains_any(text, *spec["expected_text_any"])
                unseen_results.append(
                    {
                        "case_id": spec["case_id"],
                        "prompt": spec["prompt"],
                        "expected_intent": spec["expected_intent"],
                        "actual_intent": actual_intent,
                        "outcome": r.outcome,
                        "intent_ok": intent_ok,
                        "answer_ok": answer_ok,
                    }
                )

        t_pass = sum(1 for x in train_results if x["intent_ok"])
        u_intent_pass = sum(1 for x in unseen_results if x["intent_ok"])
        u_ans_pass = sum(1 for x in unseen_results if x["answer_ok"])
        return {
            "training_intent_accuracy": round(t_pass / len(train_results), 4),
            "training_passed": t_pass,
            "training_total": len(train_results),
            "unseen_intent_accuracy": round(u_intent_pass / len(unseen_results), 4),
            "unseen_answer_accuracy": round(u_ans_pass / len(unseen_results), 4),
            "unseen_intent_passed": u_intent_pass,
            "unseen_answer_passed": u_ans_pass,
            "unseen_total": len(unseen_results),
            "training_cases": train_results,
            "unseen_cases": unseen_results,
        }

    try:
        before_stats = _run_on_db(seed_patterns=False)
        after_stats = _run_on_db(seed_patterns=True)
    finally:
        DashboardRecordService.list_records = orig_list_records  # type: ignore[method-assign]
        DashboardRecordService.list_analysis_records = orig_list_analysis  # type: ignore[method-assign]
        DashboardRecordService.list_record_index = orig_list_index  # type: ignore[method-assign]

    return {"before": before_stats, "after": after_stats}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate PMS AI conversation & routing improvements.")
    parser.add_argument("--output", type=str, default="", help="Optional path to write JSON evaluation output.")
    args = parser.parse_args()

    report = run_evaluation()
    print("=== PMS AI Evaluation Summary ===")
    for suite_name, stats in report["suites"].items():
        print(
            f"[{suite_name}] total={stats['total_cases']} followups={stats['followup_cases']} | "
            f"intent_accuracy={stats['intent_accuracy']:.2%} ({stats['intent_passed']}/{stats['total_cases']}) | "
            f"followup_context_accuracy={stats['followup_context_accuracy']:.2%} ({stats['followup_passed']}/{stats['followup_cases']}) | "
            f"answer_accuracy={stats['answer_accuracy']:.2%} ({stats['answer_passed']}/{stats['total_cases']})"
        )

    pl = report.get("pattern_learning") or {}
    if pl:
        pl_b = pl.get("before", {})
        pl_a = pl.get("after", {})
        print(
            f"[pattern_learning_before] train_intent={pl_b.get('training_intent_accuracy', 0.0):.2%} "
            f"({pl_b.get('training_passed', 0)}/{pl_b.get('training_total', 0)}) | "
            f"unseen_intent={pl_b.get('unseen_intent_accuracy', 0.0):.2%} "
            f"({pl_b.get('unseen_intent_passed', 0)}/{pl_b.get('unseen_total', 0)}) | "
            f"unseen_answer={pl_b.get('unseen_answer_accuracy', 0.0):.2%}"
        )
        print(
            f"[pattern_learning_after]  train_intent={pl_a.get('training_intent_accuracy', 0.0):.2%} "
            f"({pl_a.get('training_passed', 0)}/{pl_a.get('training_total', 0)}) | "
            f"unseen_intent={pl_a.get('unseen_intent_accuracy', 0.0):.2%} "
            f"({pl_a.get('unseen_intent_passed', 0)}/{pl_a.get('unseen_total', 0)}) | "
            f"unseen_answer={pl_a.get('unseen_answer_accuracy', 0.0):.2%}"
        )

    failures = [c for c in report["cases"] if not (c["intent_ok"] and c["followup_ok"] and c["answer_ok"])]
    if failures:
        print("\n=== Failing Cases ===")
        for f in failures:
            print(
                f"  {f['case_id']} ({f['suite']}): prompt={f['prompt']!r} | "
                f"intent_ok={f['intent_ok']} ({f['intent_reason']}) | "
                f"followup_ok={f['followup_ok']} ({f['followup_reason']}) | "
                f"answer_ok={f['answer_ok']} ({f['answer_reason']})"
            )

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nSaved JSON report to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
