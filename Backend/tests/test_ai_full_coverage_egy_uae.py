"""Comprehensive verification suite for PMS AI Full Coverage Plan (Egypt, UAE, Shared, Managerial, Corporate BSC).

Covers Phases 1–6 of `docs/plans/contextual-ai-assistant/FULL_COVERAGE_EXECUTION_PLAN.md`:
1. Coverage manifest completeness and country/level/shared denominators.
2. Wave A (Operational EGY & UAE), Wave B (RCM EGY & UAE aliases & Pre-Approvals variants),
   Wave C (Marketing, HR, IT, Offshore Admin, Shared Finance/RCM, Verified No-Data teams),
   Wave D (Egypt Managerial & Egypt/UAE Corporate BSC).
3. Full RBAC & privacy isolation matrix: Regional Manager (EGY vs UAE), Branch Director
   (allowed vs denied branch comparison), Function Director, Team/Level isolation, Self-only
   employee isolation, and mid-turn scope revocation.
4. Qwen exploration & grounded synthesis contract: production-shaped schema parity,
   discovery -> data read multi-step loop, compound 2-part evidence, fact-ID ledger
   validation (rejecting invented numbers), and separate planner/synthesis attribution.
5. Shared contextual surfaces (Monthly Review, Team Dashboard, Executive Summary, BSC,
   Employee Profile), multi-turn scope switching, fallback-data refusal, and governed
   corrective-action confirmation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from models.ai_schemas import (
    AiChatRequest,
    AiCorrectiveActionConfirmRequest,
    PageContextV1,
    SessionFilterContext,
)
from models.schemas import EvaluationData, PerformanceRecord
from services.ai.catalog import (
    ai_evidence_cache,
    canonical_team_region,
    get_ai_catalog,
    user_can_access_team,
)
from services.ai.router import _detect_teams_in_prompt
from services.ai.contextual_assistant import confirm_corrective_action_proposal
from services.corrective_action_service import CorrectiveActionAccessError
from services.ai.conversation_service import AiConversationService
from services.ai.local_data_explorer import (
    _parse_and_validate_step_payload,
    build_authorized_concept_summary,
    build_exploration_step_json_schema,
    build_fact_ledger_from_evidence,
    validate_qwen_grounded_synthesis,
)
from services.ai.orchestrator import PmsAiOrchestrator
from test_ai_workspace import (
    _build_in_memory_db,
    _make_call_center_record,
    _patch_records,
)
from test_local_assistant_exploration import _mock_llama_steps


def _make_generic_record(
    emp_id: str,
    name: str,
    team: str,
    function: str,
    score: float,
    kpi_name: str,
    kpi_actual: float,
    kpi_target: float,
    *,
    month: str = "September",
    year: int = 2026,
    position: str = "Specialist",
    region: str = "UAE",
    performance_level: str = "Employee",
    unit: str = "%",
) -> PerformanceRecord:
    ach = min(1.0, (kpi_actual / kpi_target)) if kpi_target > 0 else 1.0
    grade = "A" if score >= 95 else ("B" if score >= 85 else ("C" if score >= 75 else "D"))
    actual_val = (kpi_actual / 100.0) if unit == "%" and kpi_actual > 1.5 else kpi_actual
    target_val = (kpi_target / 100.0) if unit == "%" and kpi_target > 1.5 else kpi_target
    return PerformanceRecord(
        id=f"rec-{emp_id}-{team}-{performance_level}-{month}-{year}",
        employee_id=emp_id,
        employee_name=name,
        team=team,
        month=month,
        year=year,
        region=region if region in ("EGY", "UAE") else "EGY",
        position=position,
        performance_level=performance_level,  # type: ignore[arg-type]
        status="Below Target" if score < 80 else "On Track",
        evaluation=EvaluationData(score=score, grade=grade),
        kpi_values=[
            {
                "kpi_key": kpi_name.lower().replace(" ", "_"),
                "label": kpi_name,
                "actual_value": actual_val,
                "target_value": target_val,
                "weight_applied": 1.0,
                "contribution": ach * 1.0,
            }
        ],
    )


def test_phase1_coverage_manifest_completeness_and_country_denominators() -> None:
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "plans"
        / "contextual-ai-assistant"
        / "coverage_manifest_v1.json"
    )
    assert manifest_path.exists(), "coverage_manifest_v1.json must exist"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    summary = manifest["summary"]
    assert summary["db_teams_total"] == 38
    assert summary["db_teams_active"] == 32
    assert summary["db_teams_inactive"] == 6
    assert summary["coverage_cells_total"] == 96
    assert summary["blocked_source_cells_count"] == 0
    assert summary["unclassified_cells_count"] == 0
    assert summary["certified_cells_count"] >= 36
    assert summary["verified_no_data_cells_count"] >= 5

    cells = manifest["coverage_cells"]
    egy_certified = [c for c in cells if c["country"] == "EGY" and c["coverage_state"] == "CERTIFIED"]
    uae_certified = [c for c in cells if c["country"] == "UAE" and c["coverage_state"] == "CERTIFIED"]
    all_certified = [c for c in cells if c["country"] == "All" and c["coverage_state"] == "CERTIFIED"]
    assert len(egy_certified) >= 13
    assert len(uae_certified) >= 20
    assert len(all_certified) == 2
    assert len(egy_certified) + len(uae_certified) + len(all_certified) == summary["certified_cells_count"]


def test_phase1_country_aware_alias_disambiguation_and_catalog_coverage() -> None:
    cat = get_ai_catalog()
    assert len(cat.teams) >= 32

    # Coding EGY vs UAE Coding
    assert _detect_teams_in_prompt("coding egy") == ["Coding EGY"]
    assert _detect_teams_in_prompt("coding") == ["Coding"]
    assert canonical_team_region("Coding EGY") == "EGY"
    assert canonical_team_region("Coding") == "UAE"

    # Submission EGY vs UAE Submission
    assert _detect_teams_in_prompt("submission egy") == ["Submission EGY"]
    assert _detect_teams_in_prompt("submission") == ["Submission"]
    assert canonical_team_region("Submission EGY") == "EGY"
    assert canonical_team_region("Submission") == "UAE"

    # Resubmission (EGY) vs Re-Submission (UAE)
    assert _detect_teams_in_prompt("resubmission") == ["Resubmission"]
    assert _detect_teams_in_prompt("re-submission") == ["Re-Submission"]
    assert canonical_team_region("Resubmission") == "EGY"
    assert canonical_team_region("Re-Submission") == "UAE"

    # Pre-Approvals IP (EGY) vs Pre-Approvals IP Offshore (EGY) vs UAE Pre-Approvals variants
    assert _detect_teams_in_prompt("pre-approvals ip") == ["Pre-Approvals IP"]
    assert _detect_teams_in_prompt("pre-approvals ip offshore") == ["Pre-Approvals IP Offshore"]
    assert canonical_team_region("Pre-Approvals IP") == "EGY"
    assert canonical_team_region("Pre-Approvals IP Final Dubai") == "UAE"

    # Corporate BSC metrics registered for all 7 BSC teams
    for bsc_team in ("Marketing", "CRM", "Finance", "Nursing", "PMO", "Pharmacy", "RCM"):
        bsc_metrics = [
            m
            for m in cat.metrics.values()
            if m.team == bsc_team and m.performance_level == "Corporate"
        ]
        assert bsc_metrics, f"Missing Corporate BSC metrics for {bsc_team}"


def test_phase2_regional_branch_function_level_and_self_only_authorization_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")

    records = [
        _make_call_center_record("EMP_EGY_1", "Nour Hassan", "Inbound", 85.0, 15, 30, 40, 100),
        _make_generic_record(
            "EMP_EGY_2",
            "Tarek Ali",
            "Coding EGY",
            "RCM",
            91.0,
            "Coding Accuracy",
            96.0,
            95.0,
            region="EGY",
        ),
        _make_generic_record(
            "EMP_UAE_1",
            "Saeed Al-Mansoori",
            "Sales",
            "Sales",
            88.0,
            "Revenue Achievement",
            105.0,
            100.0,
            region="UAE",
        ),
        _make_generic_record(
            "EMP_UAE_2",
            "Fatima Al-Zaabi",
            "Coding",
            "RCM",
            93.0,
            "Coding Accuracy",
            98.0,
            95.0,
            region="UAE",
        ),
        _make_generic_record(
            "EMP_SH_1",
            "Mona Shared",
            "Finance",
            "Finance",
            89.0,
            "Report Accuracy",
            97.0,
            95.0,
            region="All",
        ),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()

    # 1. EGY Regional Manager can access EGY teams ("Inbound", "Coding EGY") and is denied UAE teams ("Sales", "Coding")
    egy_regional_scope = {
        "role": "Regional Manager",
        "region": "EGY",
        "accessible_regions": ["EGY"],
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Inbound", "Outbound", "Coding EGY", "Submission EGY", "Resubmission", "Marketing"],
        "accessible_functions": ["Call Center", "RCM", "Marketing"],
    }
    assert not user_can_access_team(egy_regional_scope, "Sales")
    assert not user_can_access_team(egy_regional_scope, "Coding")
    assert user_can_access_team(egy_regional_scope, "Coding EGY")

    with _build_in_memory_db() as db:
        # Denied UAE Sales query with 0 DB record reads
        res_denied_uae = PmsAiOrchestrator(db, egy_regional_scope).run_chat_turn(
            AiChatRequest(
                prompt="What is the Sales score in September 2026?",
                session_state=SessionFilterContext(function="Sales", month="September", year=2026),
            )
        )
        assert res_denied_uae.outcome == "restricted_access"
        assert res_denied_uae.tool_calls == []

        # Allowed EGY Coding EGY query
        _mock_llama_steps(
            monkeypatch,
            [
                {
                    "action": "call_tools",
                    "unknown_code": "none",
                    "tools": [{"tool": "get_team_score_summary", "team": "Coding EGY", "period": "2026-09"}],
                }
            ],
        )
        res_allowed_egy = PmsAiOrchestrator(db, egy_regional_scope).run_chat_turn(
            AiChatRequest(
                prompt="What is the Coding EGY score in September 2026?",
                session_state=SessionFilterContext(function="RCM", team="Coding EGY", month="September", year=2026),
            )
        )
        assert res_allowed_egy.outcome == "answer"
        assert "91.0%" in res_allowed_egy.headline

    # 2. UAE Regional Manager can access UAE teams ("Sales", "Coding") and is denied EGY ("Coding EGY", "Marketing")
    uae_regional_scope = {
        "role": "Regional Manager",
        "region": "UAE",
        "accessible_regions": ["UAE"],
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Sales", "CSR", "Pharmacy", "Coding", "Submission", "Re-Submission"],
        "accessible_functions": ["Sales", "CSR", "Pharmacy", "RCM"],
    }
    assert not user_can_access_team(uae_regional_scope, "Coding EGY")
    assert not user_can_access_team(uae_regional_scope, "Marketing")
    assert user_can_access_team(uae_regional_scope, "Sales")

    with _build_in_memory_db() as db:
        res_denied_egy = PmsAiOrchestrator(db, uae_regional_scope).run_chat_turn(
            AiChatRequest(
                prompt="What is the Coding EGY score in September 2026?",
                session_state=SessionFilterContext(function="RCM", month="September", year=2026),
            )
        )
        assert res_denied_egy.outcome == "restricted_access"
        assert res_denied_egy.tool_calls == []

    # 3. Branch Director (assigned only to Dubai) is denied a Dubai vs Sharjah comparison without substituting another branch
    dubai_director_scope = {
        "role": "Branch Director",
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Inbound"],
        "accessible_functions": ["Call Center"],
        "accessible_branches": ["dubai"],
        "accessible_team_levels": [("Inbound", "Employee")],
    }
    with _build_in_memory_db() as db:
        res_denied_branch_cmp = PmsAiOrchestrator(db, dubai_director_scope).run_chat_turn(
            AiChatRequest(
                prompt="Compare Dubai and Sharjah Inbound bookings in September 2026.",
                session_state=SessionFilterContext(function="Call Center", team="Inbound", branch="dubai", month="September", year=2026),
            )
        )
        assert res_denied_branch_cmp.outcome == "restricted_access"
        assert "Sharjah" in res_denied_branch_cmp.headline
        assert res_denied_branch_cmp.tool_calls == []


def test_phase2_mid_turn_scope_revocation_halts_exploration_and_blocks_data_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    records = [_make_call_center_record("EMP001", "Alice Example", "Inbound", 85.0, 10, 30, 40, 120)]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()

    _mock_llama_steps(
        monkeypatch,
        [
            {
                "action": "call_tools",
                "unknown_code": "none",
                "tools": [{"tool": "get_team_score_summary", "team": "Inbound", "period": "2026-09"}],
            }
        ],
    )

    initial_scope = {
        "role": "Manager",
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Inbound"],
        "accessible_functions": ["Call Center"],
        "accessible_team_levels": [("Inbound", "Employee")],
    }

    with _build_in_memory_db() as db:
        auth_service = AiConversationService(db)
        # Simulate live permission revocation during the turn (after tool execution, before response return)
        monkeypatch.setattr(
            auth_service,
            "validate_live_account_and_scope",
            lambda _s: {
                "role": "Manager",
                "has_unrestricted_team_access": False,
                "accessible_teams": ["Outbound"],
                "accessible_functions": ["Call Center"],
                "accessible_team_levels": [("Outbound", "Employee")],
            },
        )
        from services.ai.local_data_explorer import run_bounded_exploration

        res = run_bounded_exploration(
            db=db,
            scope=initial_scope,
            prompt="What is the Inbound score in September 2026?",
            session_state=SessionFilterContext(function="Call Center", team="Inbound", month="September", year=2026),
            published_periods={"2026-09"},
            employee_candidates=[],
            live_auth_service=auth_service,
        )
        assert res.handled is True
        assert res.outcome == "restricted_access"
        assert "85.0%" not in res.headline
        assert res.evidence_envelope_v2 == []


def test_phase3_all_data_waves_egy_uae_shared_managerial_and_corporate_bsc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")

    records = [
        # Wave A: EGY Support Positions (Scheduler) & UAE Sales / CSR / Pharmacy
        _make_generic_record(
            "EMP_SUP_1",
            "Hana Scheduler",
            "Support Positions",
            "Call Center",
            87.5,
            "Schedule Adherence",
            92.0,
            90.0,
            position="Scheduler",
            region="EGY",
        ),
        _make_generic_record(
            "EMP_PHARM_1",
            "Omar Pharmacist",
            "Pharmacy",
            "Pharmacy",
            92.0,
            "Prescription Accuracy",
            99.0,
            98.0,
            position="Pharmacist",
            region="UAE",
        ),
        # Wave B: EGY RCM vs UAE RCM & Pre-Approvals variants
        _make_generic_record(
            "EMP_RCM_EGY",
            "Youssef Coder",
            "Coding EGY",
            "RCM",
            88.0,
            "Coding Accuracy",
            95.0,
            95.0,
            region="EGY",
        ),
        _make_generic_record(
            "EMP_RCM_UAE",
            "Rashid Coder",
            "Coding",
            "RCM",
            94.0,
            "Coding Accuracy",
            99.0,
            95.0,
            region="UAE",
        ),
        _make_generic_record(
            "EMP_PA_UAE",
            "Layla Approver",
            "IP Elective Dubai",
            "Pre-Approvals",
            90.5,
            "Submission Within SLA",
            94.0,
            90.0,
            region="UAE",
        ),
        # Wave C: Shared Finance (region="All") & EGY HR / IT
        _make_generic_record(
            "EMP_FIN_ALL",
            "Karim Finance",
            "Finance",
            "Finance",
            86.0,
            "Audit Compliance",
            96.0,
            95.0,
            region="All",
        ),
        _make_generic_record(
            "EMP_HR_EGY",
            "Salma HR",
            "Human Resources",
            "Human Resources",
            89.5,
            "Hiring SLA",
            91.0,
            90.0,
            region="EGY",
        ),
        # Wave D: Egypt Managerial (Pre-Approvals IP)
        _make_generic_record(
            "EMP_MGR_PA",
            "Amr Manager",
            "Pre-Approvals IP",
            "Pre-Approvals",
            88.5,
            "Team SLA Compliance",
            93.0,
            90.0,
            region="EGY",
            performance_level="Managerial",
            position="Team Lead",
        ),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}

    with _build_in_memory_db() as db:
        assistant = PmsAiOrchestrator(db, admin_scope)

        # 1. Wave A: UAE Pharmacy Employee score
        _mock_llama_steps(
            monkeypatch,
            [
                {
                    "action": "call_tools",
                    "unknown_code": "none",
                    "tools": [{"tool": "get_team_score_summary", "team": "Pharmacy", "period": "2026-09"}],
                }
            ],
        )
        r_pharm = assistant.run_chat_turn(
            AiChatRequest(
                prompt="What is the Pharmacy score in September 2026?",
                session_state=SessionFilterContext(function="Pharmacy", team="Pharmacy", month="September", year=2026),
            )
        )
        assert r_pharm.outcome == "answer"
        assert "92.0%" in r_pharm.headline

        # 2. Wave B: EGY Coding EGY vs UAE Coding stay strictly separate
        _mock_llama_steps(
            monkeypatch,
            [
                {
                    "action": "call_tools",
                    "unknown_code": "none",
                    "tools": [{"tool": "get_team_score_summary", "team": "Coding EGY", "period": "2026-09"}],
                }
            ],
        )
        r_coding_egy = assistant.run_chat_turn(
            AiChatRequest(
                prompt="What is the Coding EGY score in September 2026?",
                session_state=SessionFilterContext(function="RCM", team="Coding EGY", month="September", year=2026),
            )
        )
        assert r_coding_egy.outcome == "answer"
        assert "88.0%" in r_coding_egy.headline

        _mock_llama_steps(
            monkeypatch,
            [
                {
                    "action": "call_tools",
                    "unknown_code": "none",
                    "tools": [{"tool": "get_team_score_summary", "team": "Coding", "period": "2026-09"}],
                }
            ],
        )
        r_coding_uae = assistant.run_chat_turn(
            AiChatRequest(
                prompt="What is the Coding score in September 2026?",
                session_state=SessionFilterContext(function="RCM", team="Coding", month="September", year=2026),
            )
        )
        assert r_coding_uae.outcome == "answer"
        assert "94.0%" in r_coding_uae.headline

        # 3. Wave C: Shared Finance (region="All") & Active empty team ("Collections" -> VERIFIED_NO_DATA)
        _mock_llama_steps(
            monkeypatch,
            [
                {
                    "action": "call_tools",
                    "unknown_code": "none",
                    "tools": [{"tool": "get_team_score_summary", "team": "Finance", "period": "2026-09"}],
                }
            ],
        )
        r_fin = assistant.run_chat_turn(
            AiChatRequest(
                prompt="What is the Finance Employee score in September 2026?",
                session_state=SessionFilterContext(function="Finance", team="Finance", performance_level="Employee", month="September", year=2026),
            )
        )
        assert r_fin.outcome == "answer"
        assert "86.0%" in r_fin.headline

        _mock_llama_steps(
            monkeypatch,
            [
                {
                    "action": "call_tools",
                    "unknown_code": "none",
                    "tools": [{"tool": "get_team_score_summary", "team": "Collections", "period": "2026-09"}],
                }
            ],
        )
        r_empty = assistant.run_chat_turn(
            AiChatRequest(
                prompt="What is the Collections score in September 2026?",
                session_state=SessionFilterContext(function="RCM", team="Collections", month="September", year=2026),
            )
        )
        assert r_empty.outcome == "unavailable_data"

        # 4. Wave D: Egypt Managerial (Pre-Approvals IP Managerial)
        _mock_llama_steps(
            monkeypatch,
            [
                {
                    "action": "call_tools",
                    "unknown_code": "none",
                    "tools": [
                        {
                            "tool": "get_team_score_summary",
                            "team": "Pre-Approvals IP",
                            "performance_level": "Managerial",
                            "period": "2026-09",
                        }
                    ],
                }
            ],
        )
        r_mgr = assistant.run_chat_turn(
            AiChatRequest(
                prompt="What is the Pre-Approvals IP Managerial score in September 2026?",
                session_state=SessionFilterContext(
                    function="Pre-Approvals",
                    team="Pre-Approvals IP",
                    performance_level="Managerial",
                    month="September",
                    year=2026,
                ),
            )
        )
        assert r_mgr.outcome == "answer"
        assert "88.5%" in r_mgr.headline

        # 5. Wave D: Corporate BSC (UAE CRM & EGY Marketing)
        _mock_llama_steps(
            monkeypatch,
            [
                {
                    "action": "call_tools",
                    "unknown_code": "none",
                    "tools": [
                        {
                            "tool": "get_management_balanced_scorecard",
                            "team": "CRM",
                            "performance_level": "Corporate",
                            "period": "2026-09",
                        }
                    ],
                }
            ],
        )
        r_bsc_crm = assistant.run_chat_turn(
            AiChatRequest(
                prompt="Show the CRM Corporate Balanced Scorecard in September 2026.",
                session_state=SessionFilterContext(
                    function="CRM",
                    team="CRM",
                    performance_level="Corporate",
                    month="September",
                    year=2026,
                ),
            )
        )
        assert r_bsc_crm.outcome == "answer"
        assert "CRM" in r_bsc_crm.headline
        assert "Balanced Scorecard" in r_bsc_crm.headline
        assert any("/executive" in dl.route for dl in r_bsc_crm.deep_links)


def test_phase4_discovery_then_data_read_and_grounded_synthesis_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    records = [
        _make_call_center_record("EMP001", "Alice Example", "Inbound", 80.0, 10, 30, 40, 120, month="September"),
        _make_call_center_record("EMP002", "Bob Example", "Inbound", 90.0, 20, 40, 30, 60, month="September"),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}

    # Verify that Step 1 discovery tool (`find_concepts`) continues to Step 2 (`get_team_score_summary`)
    step1_payload = {
        "action": "call_tools",
        "unknown_code": "none",
        "tools": [{"tool": "find_concepts", "team": "Inbound"}],
    }
    step2_payload = {
        "action": "call_tools",
        "unknown_code": "none",
        "tools": [{"tool": "get_team_score_summary", "team": "Inbound", "period": "2026-09"}],
    }
    # Both mock payloads must pass the exact live schema parser
    parsed1, st1 = _parse_and_validate_step_payload(json.dumps(step1_payload))
    parsed2, st2 = _parse_and_validate_step_payload(json.dumps(step2_payload))
    assert st1 == "ok" and parsed1 is not None
    assert st2 == "ok" and parsed2 is not None

    _mock_llama_steps(monkeypatch, [step1_payload, step2_payload])
    with _build_in_memory_db() as db:
        resp = PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="What is the Inbound score in September 2026?",
                session_state=SessionFilterContext(function="Call Center", month="September", year=2026),
            )
        )
    assert resp.outcome == "answer"
    assert "85.0%" in resp.headline
    assert resp.provider_usage.provider_calls in (2, 3)

    # Verify Qwen grounded synthesis validator accepts exact facts and rejects invented numbers / missing facts
    ledger = [
        {
            "fact_id": "F1",
            "part": "score",
            "subject": "Inbound",
            "period": "September 2026",
            "value": 85.0,
            "display": "85.0%",
            "unit": "%",
        },
        {
            "fact_id": "F2",
            "part": "ranking",
            "subject": "Alice Example",
            "employee_id": "EMP001",
            "team": "Inbound",
            "period": "September 2026",
            "direction": "worst",
            "value": 80.0,
            "display": "80.0%",
            "unit": "%",
        },
    ]
    valid_text, status_ok = validate_qwen_grounded_synthesis(
        draft_payload={
            "fact_ids": ["F1", "F2"],
            "headline": "Inbound scored 85.0% in September 2026, and Alice Example is the lowest performer at 80.0%.",
        },
        fact_ledger=ledger,
    )
    assert status_ok == "ok"
    assert valid_text is not None

    # Rejects invented number (e.g. 92.5%)
    bad_num_text, status_bad_num = validate_qwen_grounded_synthesis(
        draft_payload={
            "fact_ids": ["F1", "F2"],
            "headline": "Inbound scored 85.0% in September 2026 (up from 92.5%), and Alice Example scored 80.0%.",
        },
        fact_ledger=ledger,
    )
    assert bad_num_text is None
    assert status_bad_num == "invented_number"

    # Rejects missing subject
    bad_subj_text, status_bad_subj = validate_qwen_grounded_synthesis(
        draft_payload={
            "fact_ids": ["F1", "F2"],
            "headline": "Inbound scored 85.0% in September 2026, and the lowest agent scored 80.0%.",
        },
        fact_ledger=ledger,
    )
    assert bad_subj_text is None
    assert status_bad_subj == "missing_subject"


def test_phase5_contextual_surfaces_fallback_refusal_and_governed_action_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CONVERSATION_STATE_ENABLED", "false")
    records = [
        _make_call_center_record("EMP001", "Alice Example", "Inbound", 72.0, 10, 30, 35, 100, month="September"),
        _make_call_center_record("EMP002", "Bob Example", "Inbound", 92.0, 20, 40, 65, 100, month="September"),
    ]
    _patch_records(monkeypatch, records)
    ai_evidence_cache.clear()
    admin_scope = {"role": "Admin", "user_id": "admin-1", "has_unrestricted_team_access": True}
    exec_readonly_scope = {"role": "Executive", "user_id": "exec-1", "has_unrestricted_team_access": True}

    with _build_in_memory_db() as db:
        # 1. Sample/fallback page context must refuse factual answers and refuse action proposals
        res_fallback = PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="What is the score on this page and propose a corrective action?",
                page_context=PageContextV1(
                    page_id="monthly_presentation",
                    team_id="Inbound",
                    function_id="Call Center",
                    period="2026-09",
                    is_fallback_data=True,
                ),
            )
        )
        assert res_fallback.outcome == "unavailable_data"
        assert res_fallback.action_proposal is None
        assert "fallback" in res_fallback.headline.casefold()

        # 2. Proposal request on verified page context returns a draft proposal without writing to DB
        res_prop = PmsAiOrchestrator(db, admin_scope).run_chat_turn(
            AiChatRequest(
                prompt="Propose a corrective action for Inbound in September 2026",
                page_context=PageContextV1(
                    page_id="team_dashboard",
                    team_id="Inbound",
                    function_id="Call Center",
                    period="2026-09",
                    is_fallback_data=False,
                ),
            )
        )
        assert res_prop.capability_mode == "proposal"
        assert res_prop.action_proposal is not None
        assert res_prop.action_proposal.can_user_create_action is True
        assert res_prop.action_proposal.persisted_status_on_save == "Open"

        # 3. Read-only Executive cannot confirm/save the corrective action proposal
        confirm_req = AiCorrectiveActionConfirmRequest(
            proposal_id=res_prop.action_proposal.proposal_id,
            team="Inbound",
            month="September",
            year=2026,
            employee_id=res_prop.action_proposal.employee_id,
            linked_kpi_key=res_prop.action_proposal.linked_kpi_key,
            action_type=res_prop.action_proposal.action_type,
            priority=res_prop.action_proposal.priority,
            action_text=res_prop.action_proposal.proposed_action_text,
            root_cause_note=res_prop.action_proposal.proposed_root_cause_note,
            evidence_revision=res_prop.action_proposal.evidence_revision,
        )
        with pytest.raises(CorrectiveActionAccessError):
            confirm_corrective_action_proposal(
                db=db,
                scope=exec_readonly_scope,
                body=confirm_req,
            )
