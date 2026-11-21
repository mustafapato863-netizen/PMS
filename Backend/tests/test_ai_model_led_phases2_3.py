"""Phase 2 & Phase 3 verification tests:
- Scoped catalog discovery (`discover_pms_catalog`) with strict RBAC exclusion.
- Bounded discovery/planning loop (discovery -> analytical tool -> verified answer, plus duplicate-call early stop).
- Bounded 1-attempt synthesis repair when Pass 2 fails claim validation.
- Multi-turn drill-down journeys (`in it`, `leading team`, `second one`, Marketing role -> employee,
  country/month override, tied scores, no-data period, and mid-conversation permission revocation).
"""
from __future__ import annotations

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import AiChatRequest, SessionFilterContext
from models.schemas import EvaluationData, PerformanceRecord
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.tool_registry import DeterministicToolRegistry, ToolExecutionContext
from services.dashboard_record_service import DashboardRecordService
from services.database_record_source import DatabaseRecordSource
from tests.ai_provider_fakes import (
    failed_response,
    install_scripted_provider,
    ok_response,
    tool_response,
)


def synthesis_response(headline: str, bullets: list[str] | None = None):
    return ok_response(
        json.dumps({"headline": headline, "narrative_bullets": bullets or []}),
        provider="nvidia",
        model="nvidia/test-alternate-model",
    )


def _rec(
    emp_id: str,
    name: str,
    team: str,
    region: str,
    score: float,
    *,
    month: str = "September",
    year: int = 2026,
    position: str = "Agent",
    branch: str = "dubai",
    level: str = "Employee",
) -> PerformanceRecord:
    team_kpis = [
        {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": score, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
    ]
    default_kpi = {
        "Inbound": ("Quality", "Quality Score", 100.0, "%"),
        "Outbound": ("Quality", "Quality Score", 100.0, "%"),
        "Pharmacy": ("TenderCompliance", "Tender Compliance", 100.0, "%"),
        "Sales": ("OPCensus", "OP Census Ach", 100.0, "number"),
        "Submission": ("submission_within_due_date", "Submission Within Due Date", 100.0, "%"),
        "Coding": ("QualityErrors", "Quality Errors", 3.0, "%"),
    }.get(team)
    if default_kpi is not None and default_kpi[0] != "QualityErrors":
        k_key, k_label, k_tgt, k_unit = default_kpi
        team_kpis.append({"kpi_key": k_key, "label": k_label, "actual_value": score, "target_value": k_tgt, "unit": k_unit, "direction": "higher_better"})
    return PerformanceRecord(
        id=f"{team}_{emp_id}_{year}_{month[:3]}",
        employee_id=emp_id,
        employee_name=name,
        team=team,
        position=position,
        region=region,
        branch=branch,
        month=month,
        year=year,
        performance_level=level,
        status="On Track" if score >= 80 else "Below Target",
        evaluation=EvaluationData(score=score, grade="A" if score >= 90 else "B"),
        kpi_values=team_kpis,
    )


def _db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    return sessionmaker(bind=eng)()


def _patch_records(monkeypatch, records: list[PerformanceRecord]) -> None:
    monkeypatch.setattr(DatabaseRecordSource, "get_all", lambda *a, **kw: list(records))
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda *a, **kw: list(records))
    monkeypatch.setattr(DashboardRecordService, "list_record_index", lambda *a, **kw: None)


def _sample_records() -> list[PerformanceRecord]:
    return [
        # EGY Sep 2026: Call Center (Inbound 95.0, Outbound 88.0), Marketing (roles)
        _rec("E-IN-1", "Nour Top", "Inbound", "EGY", 96.0),
        _rec("E-IN-2", "Salma Tie", "Inbound", "EGY", 95.0),
        _rec("E-IN-3", "Tarek Tie", "Inbound", "EGY", 95.0),
        _rec("E-IN-4", "Karim Fourth", "Inbound", "EGY", 94.0),
        _rec("E-OUT-1", "Hossam Out", "Outbound", "EGY", 89.0),
        _rec("E-OUT-2", "Laila Out", "Outbound", "EGY", 87.0),
        _rec("E-MKT-1", "Mona Director", "Marketing", "EGY", 98.4, position="Creative Director"),
        _rec("E-MKT-2", "Youssef Writer", "Marketing", "EGY", 94.0, position="Content Writer"),
        _rec("E-MKT-3", "Rana Designer", "Marketing", "EGY", 88.0, position="Graphic Designer"),
        # EGY Aug 2026: different leader
        _rec("E-IN-1", "Nour Top", "Inbound", "EGY", 82.0, month="August"),
        _rec("E-MKT-1", "Mona Director", "Marketing", "EGY", 91.0, month="August", position="Creative Director"),
        # UAE Aug 2026 (no UAE Sep 2026)
        _rec("U-RCM-1", "Zayed Coder", "Coding", "UAE", 97.5, month="August", branch="dubai"),
        _rec("U-SAL-1", "Amina Sales", "Sales", "UAE", 75.0, month="August", branch="sharjah"),
    ]


def test_verified_comparison_uses_exact_pms_scores_and_retains_both_teams(monkeypatch):
    _patch_records(monkeypatch, [
        *_sample_records(),
        _rec("E-OUT-1", "Hossam Out", "Outbound", "EGY", 82.0, month="August"),
        _rec("U-PHA-1", "Dina Tariq", "Pharmacy", "UAE", 87.5, month="July", position="Pharmacist"),
        _rec("U-PHA-1", "Dina Tariq", "Pharmacy", "UAE", 90.5, month="September", position="Pharmacist"),
    ])
    ai_evidence_cache.clear()
    with _db() as db:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "adm-scores", "has_unrestricted_team_access": True})

        def ask(prompt, previous=None):
            return orch.run_chat_turn(AiChatRequest(
                prompt=prompt,
                conversation_id=previous.conversation_id if previous else None,
                session_state=previous.resolved_session_state if previous else SessionFilterContext(
                    month="September", year=2026,
                ),
                provider_override="deterministic",
            ))

        change = ask("How did Pharmacy’s average score change from July to September 2026 in UAE?")
        assert change.outcome == "answer", change.headline
        assert all(text in change.headline for text in ("87.5%", "90.5%", "3.0 percentage points"))
        assert [e.period for e in change.typed_evidence] == ["July 2026", "September 2026"]
        rephrase = ask(
            "For the same team, which of those two months had the higher overall score and by how many percentage points?",
            change,
        )
        assert all(text in rephrase.headline for text in ("87.5%", "90.5%", "3.0 percentage points")), rephrase.headline
        missing = ask("How did Pharmacy’s average score change from July to August 2026 in UAE?")
        assert missing.outcome == "unavailable_data"
        assert "Pharmacy in August 2026" in missing.headline

        tie = ask(
            "Back to Egypt. Compare Inbound and Outbound in August 2026. "
            "Which team scored higher, and by how many points?", change,
        )
        assert tie.outcome == "answer", tie.headline
        assert all(text in tie.headline for text in ("Inbound", "Outbound", "82.0%", "tied"))
        followup = ask("And in September, how do those two teams compare?", tie)
        assert followup.outcome == "answer", followup.headline
        assert all(text in followup.headline for text in ("95.0%", "88.0%", "7.0 percentage points"))
        assert followup.narrative_bullets == []


def test_workspace_replies_keep_confirmed_ranking_and_subject(monkeypatch):
    _patch_records(monkeypatch, [
        *_sample_records(),
        _rec("U-SAL-1", "Amina Sales", "Sales", "UAE", 95, branch="sharjah"),
        _rec("U-IN-1", "Nader Lowest", "Inbound", "UAE", 61, branch="dubai"),
    ])
    ai_evidence_cache.clear()
    with _db() as db:
        orch = PmsAiOrchestrator(db, {
            "role": "Admin", "user_id": "ranked-workspace-followups", "has_unrestricted_team_access": True,
        })

        def ask(prompt, last=None):
            return orch.run_chat_turn(AiChatRequest(
                prompt=prompt,
                conversation_id=last.conversation_id if last else None,
                session_state=last.resolved_session_state if last else SessionFilterContext(month="September", year=2026),
                provider_override="deterministic",
            ))

        ranking = ask("who is best department in sep for UAE")
        assert "Best department" in ranking.headline and "Sales" in ranking.headline
        assert "Amina Sales" not in ranking.headline
        thanks = ask("ok thank you", ranking)
        assert thanks.headline.startswith("You're") and not thanks.tool_calls

        top = ask("Show the top 3 employees in Inbound Egypt in September 2026", thanks)
        low = ask("in worst 3", top)
        assert "Bottom 3 employees in Inbound" in low.headline
        results = low.resolved_session_state.last_confirmed_query.ranking_results
        assert [result.name for result in results][:1] == ["Karim Fourth"]
        assert all(result.region == "EGY" and result.period == "2026-09" for result in results)
        recommendation = ask("what is your recommened action for worst one ?", low)
        assert recommendation.action_proposal is not None
        assert recommendation.action_proposal.employee_name == "Karim Fourth"
        assert recommendation.action_proposal.actual_display == "94.0%"
        repeated = ask("what is your recommened action for worst one ?", recommendation)
        assert repeated.action_proposal is not None
        assert repeated.action_proposal.employee_id == recommendation.action_proposal.employee_id


def test_kpi_diagnosis_does_not_confuse_reported_rate_with_proven_score_impact():
    from models.ai_schemas import TypedMetricEvidence
    from services.ai.verified_answers import answer_kpi_question

    base = {
        "team": "Coding EGY", "period": "October 2026", "source_link": "/insights",
        "actual_display": "17.2%", "weight_percent": 50,
    }
    rejection = TypedMetricEvidence(
        **base, metric_id="coding:rejection", kpi_key="rejection", display_name="Rejection Rate",
        contributes_to_score=False,
    )
    turnaround = TypedMetricEvidence(
        **{**base, "actual_display": "81.0%", "weight_percent": 30},
        metric_id="coding:tat", kpi_key="tat", display_name="TAT",
        achievement_percent=90, target_display="90.0%",
    )
    headline, notes, focus = answer_kpi_question("gap", None, [rejection, turnaround], [], False)
    assert focus == turnaround
    assert "81.0% vs 90.0%" in headline and "Rejection Rate" in notes[0]
    headline, notes, focus = answer_kpi_question("impact", "Rejection Rate", [rejection, turnaround], [], True)
    assert focus == rejection and not notes
    assert "17.2%" in headline and "can't verify its score impact" in headline
    headline, _, focus = answer_kpi_question("weight", "coding:tat", [rejection, turnaround], [], False)
    assert focus == turnaround and "30% configured scorecard weight" in headline


def test_cohort_result_survives_a_conflicting_model_plan(monkeypatch):
    records = [
        _rec("U-SAL-1", "Amina Sales", "Sales", "UAE", 78.0, month="August"),
        _rec("U-SAL-2", "Nora Sales", "Sales", "UAE", 74.0, month="August"),
        _rec("U-SAL-1", "Amina Sales", "Sales", "UAE", 96.0, month="September"),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    calls = install_scripted_provider(monkeypatch, [
        tool_response("query_rankings", entity="employee", region="EGY", period="2026-09", limit=1),
    ])
    with _db() as db:
        resp = PmsAiOrchestrator(db, {"role": "Admin", "has_unrestricted_team_access": True}).run_chat_turn(AiChatRequest(
            prompt="How did the Sales cohort score overall in August 2026 over in the Emirates?",
            session_state=SessionFilterContext(month="September", year=2026),
            provider_override="auto",
        ))
        assert resp.outcome == "answer"
        assert "76.0%" in resp.headline
        assert "Sales" in resp.headline
        assert "August 2026" in resp.headline
        assert "Monthly Review team score" in resp.headline
        assert resp.resolved_session_state.region == "UAE"
        assert [call.tool_name for call in resp.tool_calls] == ["get_kpi_diagnosis_and_trends"]
        assert len(calls) == 1
        assert "exact month(s)" in str(calls[0])


def test_composable_rankings_use_scoped_wait_times_and_original_units(monkeypatch):
    from scripts.run_phase6_independent_eval import build_synthetic_holdout_records

    _patch_records(monkeypatch, [*build_synthetic_holdout_records(), _rec("NO-WAIT", "Unmeasured", "Inbound", "EGY", 100)])
    with _db() as db:
        registry = DeterministicToolRegistry(ToolExecutionContext(
            db=db, scope={"role": "Admin", "has_unrestricted_team_access": True}, session_state=SessionFilterContext(),
        ))
        actual = registry.execute_query_rankings(entity="employee", team="Inbound", region="EGY", period="2026-09",
                                                 metric_id="inbound:waitingtime", sort_order="asc", limit=1)
        assert actual.typed_evidence[0].employee_name == "Nadia Mansour"
        assert actual.typed_evidence[0].actual == 3.4 and actual.typed_evidence[0].unit == "min"
        assert actual.typed_evidence[0].direction == "lower_better"
        assert "min" in actual.visual_cards[0].items[0].badge_text
        from urllib.parse import parse_qs, urlparse
        link = parse_qs(urlparse(actual.deep_links[0].route).query)
        assert link == {"period": ["2026-09"], "region": ["egy"], "deepDive": ["call-center"], "team": ["Inbound"]}


@pytest.mark.parametrize("provider_override", ["deterministic", "auto"])
def test_named_kpi_ranking_excludes_unmeasured_employees(monkeypatch, provider_override):
    from scripts.run_phase6_independent_eval import build_synthetic_holdout_records

    _patch_records(monkeypatch, [
        *build_synthetic_holdout_records(),
        _rec("NO-WAIT", "Unmeasured Employee", "Inbound", "EGY", 100.0),
    ])
    ai_evidence_cache.clear()
    if provider_override == "auto":
        monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
        install_scripted_provider(monkeypatch, [
            tool_response(
                "rank_employees", team="Inbound", metric_id="inbound:waitingtime",
                period="2026-09", direction="worst", limit=1,
            ),
            synthesis_response(
                "Nadia Mansour had the shortest wait time at 3.4 min in Inbound, Egypt, in September 2026.",
                ["Nadia Mansour: 3.4 min"],
            ),
        ])
    with _db() as db:
        resp = PmsAiOrchestrator(db, {"role": "Admin", "has_unrestricted_team_access": True}).run_chat_turn(AiChatRequest(
            prompt="Which employee in Inbound logged the shortest wait time during September 2026 in Egypt?",
            session_state=SessionFilterContext(month="September", year=2026),
            provider_override=provider_override,
        ))
        assert resp.outcome == "answer"
        assert "Unmeasured Employee" not in resp.headline
        assert "Nadia Mansour" in resp.headline
        assert any(ev.kpi_key == "waitingtime" and ev.actual == 3.4 and ev.unit == "min" for ev in resp.typed_evidence)


@pytest.mark.parametrize("draft,source", [
    ("Dubai had the better overall score in June 2026 with 88.5%, compared to Sharjah with 81.0%.", "model_synthesis"),
    ("Pharmacy Dubai achieved a better overall score than Sharjah in June 2026.", "fallback"),
])
def test_model_branch_comparison_retains_verified_department(monkeypatch, draft, source):
    from scripts.run_phase6_independent_eval import build_synthetic_holdout_records

    _patch_records(monkeypatch, build_synthetic_holdout_records())
    ai_evidence_cache.clear()
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(monkeypatch, [
        tool_response("compare_branches", team="Pharmacy", branches=["dubai", "sharjah"],
                      metric="overall_score", period="2026-06"),
        synthesis_response(
            draft,
            ["Dubai: 88.5%", "Sharjah: 81.0%"],
        ),
    ])
    with _db() as db:
        resp = PmsAiOrchestrator(db, {"role": "Admin", "has_unrestricted_team_access": True}).run_chat_turn(AiChatRequest(
            prompt="Which Pharmacy location had the better overall score in June 2026, Dubai or Sharjah?",
            session_state=SessionFilterContext(month="September", year=2026),
            provider_override="auto",
        ))
        assert resp.answer_source == source, (resp.headline, resp.provider_usage.fallback_outcome)
        assert "Pharmacy" in resp.headline and "88.5%" in resp.headline and "81.0%" in resp.headline


def test_discover_pms_catalog_enforces_rbac_and_reports_role_based_departments(monkeypatch):
    records = _sample_records()
    _patch_records(monkeypatch, records)
    db = _db()
    try:
        # 1. Admin discovers Egypt & UAE, Marketing role_based_single_team=True, and regional periods
        admin_scope = {"role": "Admin", "user_id": "adm-1", "has_unrestricted_team_access": True}
        admin_reg = DeterministicToolRegistry(ToolExecutionContext(db=db, scope=admin_scope, session_state=SessionFilterContext()))
        res = admin_reg.execute_model_led_tool("discover_pms_catalog", {"kind": "all"})
        disc = res.digest["catalog_discovery"]
        dept_map = {d["department"]: d for d in disc["departments"]}
        assert "Call Center" in dept_map
        assert "Marketing" in dept_map
        assert dept_map["Marketing"]["role_based_single_team"] is True
        assert "2026-09" in disc["published_periods_by_region"]["EGY"]
        assert "2026-09" not in disc["published_periods_by_region"].get("UAE", [])
        assert "2026-08" in disc["published_periods_by_region"]["UAE"]

        # 2. Scoped Manager restricted to Outbound in EGY NEVER discovers Inbound, Marketing, or UAE entities
        mgr_scope = {
            "role": "Manager",
            "user_id": "mgr-1",
            "has_unrestricted_team_access": False,
            "accessible_teams": ["Outbound"],
            "accessible_regions": ["EGY"],
        }
        mgr_reg = DeterministicToolRegistry(ToolExecutionContext(db=db, scope=mgr_scope, session_state=SessionFilterContext()))
        mgr_res = mgr_reg.execute_model_led_tool("discover_pms_catalog", {"kind": "all"})
        mgr_disc = mgr_res.digest["catalog_discovery"]
        found_teams = {t["team"] for t in mgr_disc["teams"]}
        found_emps = {e["employee_id"] for e in mgr_disc["employees"]}
        assert found_teams == {"Outbound"}
        assert "Inbound" not in found_teams
        assert "Marketing" not in found_teams
        assert "Coding" not in found_teams
        assert found_emps == {"E-OUT-1", "E-OUT-2"}

        # 3. Self-only employee only discovers their own employee record
        emp_scope = {
            "role": "Employee",
            "user_id": "emp-1",
            "is_self_only": True,
            "employee_id": "E-IN-1",
            "accessible_teams": ["Inbound"],
        }
        emp_reg = DeterministicToolRegistry(ToolExecutionContext(db=db, scope=emp_scope, session_state=SessionFilterContext()))
        emp_res = emp_reg.execute_model_led_tool("discover_pms_catalog", {"kind": "employee"})
        assert [e["employee_id"] for e in emp_res.digest["catalog_discovery"]["employees"]] == ["E-IN-1"]
    finally:
        db.close()


def test_bounded_discovery_loop_and_duplicate_early_stop(monkeypatch):
    records = _sample_records()
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")

    # Round 1: planner asks for catalog discovery -> Round 2: planner calls query_rankings -> Pass 2: grounded synthesis
    calls = install_scripted_provider(
        monkeypatch,
        [
            tool_response("discover_pms_catalog", query="Marketing", kind="all", region="EGY"),
            tool_response("query_rankings", entity="team", department="Marketing", region="EGY", period="2026-09", limit=1),
            synthesis_response(
                "The top role in Marketing in Egypt for September 2026 is Creative Director at 98.4% (1 evaluated employee).",
                ["Creative Director ranked first with 98.4% across 1 evaluated employee."],
            ),
        ],
    )

    db = _db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "adm-disc", "has_unrestricted_team_access": True})
        resp = orch.run_chat_turn(
            AiChatRequest(
                prompt="Which team led Marketing in Egypt in September 2026?",
                session_state=SessionFilterContext(month="September", year=2026),
                provider_override="auto",
            )
        )
        assert resp.outcome == "answer"
        assert resp.answer_source == "model_synthesis"
        assert "Creative Director" in resp.headline
        assert "98.4%" in resp.headline
        assert [tc.tool_name for tc in resp.tool_calls] == ["discover_pms_catalog", "query_rankings"]
        assert len(calls) == 3

        # Duplicate discovery call early-stop: planner repeats identical discover_pms_catalog call -> stops immediately
        dup_calls = install_scripted_provider(
            monkeypatch,
            [
                tool_response("discover_pms_catalog", query="Marketing", kind="all", region="EGY"),
                tool_response("discover_pms_catalog", query="Marketing", kind="all", region="EGY"),
                tool_response("discover_pms_catalog", query="Marketing", kind="all", region="EGY"),
            ],
        )
        resp_dup = orch.run_chat_turn(
            AiChatRequest(
                prompt="Tell me what Marketing scopes exist in Egypt",
                session_state=SessionFilterContext(month="September", year=2026),
                provider_override="auto",
            )
        )
        assert resp_dup.outcome == "answer"
        # Stopped after 1 discovery read + 1 follow-up planner call that repeated the identical signature
        assert [tc.tool_name for tc in resp_dup.tool_calls] == ["discover_pms_catalog"]
        assert len(dup_calls) == 2
    finally:
        db.close()


def test_model_optional_filters_and_explicit_abbreviated_period(monkeypatch):
    _patch_records(monkeypatch, _sample_records())
    ai_evidence_cache.clear()
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    install_scripted_provider(monkeypatch, [
        tool_response("query_rankings", entity="department", group_by="none",
                      region="UAE", department="null", position="undefined",
                      sort_order="desc", period="2026-10", limit=1),
        synthesis_response("RCM led by average employee score at 97.5% in August 2026.", []),
    ])
    with _db() as db:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "scope-resolution", "has_unrestricted_team_access": True})
        answer = orch.run_chat_turn(AiChatRequest(
            prompt="Which department performed best in UAE in Aug 2026?",
            session_state=SessionFilterContext(month="October", year=2026),
            provider_override="auto",
        ))
        assert answer.outcome == "answer", answer.headline
        assert answer.resolved_session_state.month == "August"
        assert "97.5" in answer.headline


def test_bounded_synthesis_repair_succeeds_on_second_attempt_and_falls_back_if_still_invalid(monkeypatch):
    records = _sample_records()
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")

    db = _db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "adm-repair", "has_unrestricted_team_access": True})

        # Case 1: First synthesis hallucinates 99.9% -> bounded repair returns verified 93.5% -> accepted
        calls = install_scripted_provider(
            monkeypatch,
            [
                tool_response("query_rankings", entity="department", region="EGY", period="2026-09", limit=1),
                synthesis_response("Marketing led Egypt in September 2026 at 99.9%."),  # fails claim check!
                synthesis_response("Marketing led Egypt in September 2026 with an average score of 93.5%."),
            ],
        )
        # Actual EGY Sep 2026 averages: Marketing=(98.4+94+88)/3=93.47 -> 93.5%, Call Center=(96+95+95+94+89+87)/6=92.67 -> 92.7%
        resp = orch.run_chat_turn(
            AiChatRequest(
                prompt="Which department led Egypt in September 2026?",
                session_state=SessionFilterContext(month="September", year=2026),
                provider_override="auto",
            )
        )
        assert resp.outcome == "answer"
        assert resp.answer_source == "model_synthesis"
        assert "Marketing" in resp.headline
        assert "93.5%" in resp.headline
        assert len(calls) == 3  # 1 planner + 1 initial synth + 1 bounded repair

        # Case 2: Both initial synthesis and bounded repair fail -> falls back truthfully to verified deterministic facts
        calls2 = install_scripted_provider(
            monkeypatch,
            [
                tool_response("query_rankings", entity="department", region="EGY", period="2026-09", limit=1),
                synthesis_response("Marketing led Egypt at 99.9%."),
                synthesis_response("Marketing led Egypt at 88.8%."),
            ],
        )
        resp2 = orch.run_chat_turn(
            AiChatRequest(
                prompt="What was the best department in Egypt for September 2026?",
                session_state=SessionFilterContext(month="September", year=2026),
                provider_override="auto",
            )
        )
        assert resp2.outcome == "answer"
        assert resp2.answer_source == "fallback"
        assert "Marketing" in resp2.headline
        assert "93.5%" in resp2.headline
        assert "99.9%" not in resp2.headline
        assert "88.8%" not in resp2.headline
        assert len(calls2) == 3  # strictly bounded to 1 repair
    finally:
        db.close()


def test_nvidia_autocorrects_rejected_aggregate_ranking(monkeypatch):
    from services.ai import nemotron_analyzer

    _patch_records(monkeypatch, _sample_records())
    ai_evidence_cache.clear()
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_NVIDIA_AUTO_REPAIR_ENABLED", "true")
    monkeypatch.setattr(nemotron_analyzer, "is_feedback_analyzer_configured", lambda: True)
    monkeypatch.setattr(nemotron_analyzer, "_consume_daily_budget", lambda: True)
    drafts = iter(["Marketing led at 93.5%.", "Marketing led at 99.9%."])
    received = []

    def fake_nvidia(messages, **kwargs):
        received.append(messages)
        assert 0 < kwargs["timeout_seconds"] <= 20
        return {"headline": next(drafts)}

    monkeypatch.setattr(nemotron_analyzer, "_post_nvidia_chat_completions", fake_nvidia)
    with _db() as db:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "adm-nvidia", "has_unrestricted_team_access": True})
        for expected_source in ("model_synthesis", "fallback"):
            calls = install_scripted_provider(monkeypatch, [
                tool_response("query_rankings", entity="department", region="EGY", period="2026-09", limit=1),
                synthesis_response("Marketing led Egypt at 99.9%."),
            ])
            response = orch.run_chat_turn(AiChatRequest(
                prompt="Which department led Egypt in September 2026?",
                session_state=SessionFilterContext(month="September", year=2026),
                provider_override="auto",
            ))
            assert len(calls) == 2
            assert response.answer_source == expected_source
            assert "93.5%" in response.headline and "99.9%" not in response.headline
            if expected_source == "model_synthesis":
                assert response.provider_used == "nvidia"
        assert len(received) == 2
        assert all("Nour Top" not in str(message) and "99.9" not in str(message) for message in received)


def test_multiturn_drilldown_second_one_marketing_roles_and_explicit_overrides(monkeypatch):
    records = _sample_records()
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    db = _db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "adm-journeys", "has_unrestricted_team_access": True})

        # Journey 1: Call Center teams -> leading team top 3 -> second one top 2 -> explicit country/month override
        r1 = orch.run_chat_turn(AiChatRequest(
            prompt="Which two teams performed best in Call Center in Egypt in September 2026?",
            session_state=SessionFilterContext(month="October", year=2026),
            provider_override="deterministic",
        ))
        assert r1.outcome == "answer"
        assert "Inbound" in r1.headline
        assert r1.resolved_session_state.last_confirmed_query is not None
        assert len(r1.resolved_session_state.last_confirmed_query.ranking_results) == 2

        r2 = orch.run_chat_turn(AiChatRequest(
            conversation_id=r1.conversation_id,
            prompt="Who were the top three in the leading team?",
            session_state=r1.resolved_session_state,
            provider_override="deterministic",
        ))
        assert r2.outcome == "answer"
        r2_txt = r2.headline + " " + " ".join(r2.narrative_bullets)
        assert "Nour Top" in r2_txt
        assert "Salma Tie" in r2_txt
        assert "Tarek Tie" in r2_txt
        assert "Hossam Out" not in r2_txt

        # Drill into "the second one" (Outbound) right after r1
        r2_second = orch.run_chat_turn(AiChatRequest(
            conversation_id=r1.conversation_id,
            prompt="Who were the top 2 employees in the second one?",
            session_state=r1.resolved_session_state,
            provider_override="deterministic",
        ))
        assert r2_second.outcome == "answer"
        r2s_txt = r2_second.headline + " " + " ".join(r2_second.narrative_bullets)
        assert "Hossam Out" in r2s_txt
        assert "Laila Out" in r2s_txt
        assert "Nour Top" not in r2s_txt

        # Explicit country + month change supersedes remembered Egypt/September
        r3_override = orch.run_chat_turn(AiChatRequest(
            conversation_id=r1.conversation_id,
            prompt="What was the best department in UAE in August 2026?",
            session_state=r2.resolved_session_state,
            provider_override="deterministic",
        ))
        assert r3_override.outcome == "answer"
        assert "RCM" in r3_override.headline
        assert r3_override.resolved_session_state.region == "UAE"
        assert r3_override.resolved_session_state.month == "August"

        # Journey 2: Marketing -> role -> best employee in it (fresh chat)
        m1 = orch.run_chat_turn(AiChatRequest(
            prompt="What is the best team in Marketing in Egypt in September 2026?",
            session_state=SessionFilterContext(month="September", year=2026),
            provider_override="deterministic",
        ))
        assert m1.outcome == "answer"
        assert "role" in m1.headline.lower()
        assert "Creative Director" in m1.headline
        assert "1 evaluated employee" in m1.headline

        m2 = orch.run_chat_turn(AiChatRequest(
            conversation_id=m1.conversation_id,
            prompt="Who was best in it?",
            session_state=m1.resolved_session_state,
            provider_override="deterministic",
        ))
        assert m2.outcome == "answer"
        assert "Mona Director" in m2.headline
        assert "98.40%" in m2.headline
    finally:
        db.close()


def test_model_led_non_person_team_ranking_redirects_rank_employees_to_query_rankings(monkeypatch):
    """If the model picks rank_employees for a 'best team in Marketing' question, PMS enforces entity='team' -> role ranking."""
    records = _sample_records()
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    monkeypatch.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")

    install_scripted_provider(
        monkeypatch,
        [
            tool_response("rank_employees", team="Marketing", period="2026-09", limit=1),
            synthesis_response(
                "The top role in Marketing in Egypt in September 2026 is Creative Director at 98.4% (1 evaluated employee).",
                ["Creative Director led Marketing roles with 98.4%."],
            ),
        ],
    )
    db = _db()
    try:
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": "adm-ent-guard", "has_unrestricted_team_access": True})
        resp = orch.run_chat_turn(
            AiChatRequest(
                prompt="What is the best team in Marketing in Egypt in September 2026?",
                session_state=SessionFilterContext(month="September", year=2026),
                provider_override="auto",
            )
        )
        assert resp.outcome == "answer"
        assert resp.answer_source == "model_synthesis"
        assert "Creative Director" in resp.headline
        assert "98.4%" in resp.headline
        assert any(tc.tool_name == "query_rankings" for tc in resp.tool_calls)
    finally:
        db.close()
