"""Comprehensive unit and integration tests for the PMS Contextual AI Assistant (Phases 2, 3, 5, and 6)."""

from __future__ import annotations

import datetime as dt
import urllib.request
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import (
    AiChatRequest,
    AiCorrectiveActionConfirmRequest,
    PageContextV1,
    SessionFilterContext,
)
from models.models import Action, Employee, Team
from models.schemas import CallsData, EvaluationData, GeoBreakdown, GeoData, PerformanceRecord
from services.ai.catalog import ai_evidence_cache
from services.ai.contextual_assistant import (
    ProposalStaleEvidenceError,
    confirm_corrective_action_proposal,
)
from services.ai.local_model_router import (
    ALLOWED_INTENTS,
    build_intent_json_schema,
    suggest_intent,
)
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.trace_logger import TraceOwnershipError, TrainingTraceLogger
from services.cache_invalidation_service import CacheInvalidationService
from services.corrective_action_service import (
    CorrectiveActionAccessError,
    CorrectiveActionValidationError,
)
from services.dashboard_record_service import DashboardRecordService


def _build_in_memory_db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def _make_inbound_record(
    emp_id: str,
    name: str,
    score: float,
    booking_actual: float,
    booking_target: float = 0.30,
    attendance_actual: float = 0.68,
    attendance_target: float = 0.65,
    abandon_actual: float = 0.04,
    abandon_target: float = 0.05,
    month: str = "September",
    year: int = 2026,
) -> PerformanceRecord:
    return PerformanceRecord(
        id=f"Inbound_{emp_id}_{year}_{month[:3]}",
        employee_id=emp_id,
        employee_name=name,
        team="Inbound",
        month=month,
        year=year,
        region="UAE",
        position="Call Center Agent",
        performance_level="Employee",
        status="Below Target" if score < 80 else "On Track",
        evaluation=EvaluationData(
            score=score,
            grade="B" if score >= 80 else "C",
        ),
        calls=CallsData(inbound=400, total_handled=500, abandoned=20),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=110, sharjah=40, ajman=20, clinics=10),
            attended=GeoBreakdown(dubai=74, sharjah=28, ajman=14, clinics=6),
        ),
        kpi_values=[
            {
                "kpi_key": "Attendance",
                "label": "Patient Attendance Rate",
                "actual_value": attendance_actual,
                "target_value": attendance_target,
                "weight_applied": 0.70,
                "contribution": min(attendance_actual / attendance_target, 1.0) * 0.70,
            },
            {
                "kpi_key": "Booking",
                "label": "Booking Rate",
                "actual_value": booking_actual,
                "target_value": booking_target,
                "weight_applied": 0.20,
                "contribution": min(booking_actual / booking_target, 1.0) * 0.20,
            },
            {
                "kpi_key": "Other",
                "label": "Abandon Rate",
                "actual_value": abandon_actual,
                "target_value": abandon_target,
                "weight_applied": 0.10,
                "contribution": 0.08,
            },
        ],
    )


def _patch_records(monkeypatch: pytest.MonkeyPatch, records: list[PerformanceRecord]) -> None:
    monkeypatch.setattr(DashboardRecordService, "list_records", lambda _self, **_kw: records)
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda _self, **_kw: records)
    monkeypatch.setattr(DashboardRecordService, "list_record_index", lambda _self: None)


def test_page_context_resolution_precedence_and_filter_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify PageContextV1 precedence (explicit prompt > selected entity/metric > page filter > conversation)
    and context label synchronization when filters change."""
    db = _build_in_memory_db()
    inb_rec = _make_inbound_record("EMP101", "Sara Mahmoud", 82.5, booking_actual=0.22, booking_target=0.30)
    out_rec = _make_inbound_record("EMP202", "Omar Khaled", 91.0, booking_actual=0.34, booking_target=0.30)
    out_rec.team = "Outbound"
    out_rec.id = "Outbound_EMP202_2026_Sep"
    _patch_records(monkeypatch, [inb_rec, out_rec])
    ai_evidence_cache.clear()

    gm_scope = {
        "role": "General Manager",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "has_unrestricted_team_access": True,
    }
    orch = PmsAiOrchestrator(db, gm_scope)

    # 1. Page context provides team=Inbound, period=2026-09, selected_metric_id=Booking
    res_t1 = orch.run_chat_turn(
        AiChatRequest(
            prompt="Why is this metric below target?",
            page_context=PageContextV1(
                page_id="monthly_presentation",
                route_id="/monthly-presentation",
                function_id="Call Center",
                team_id="Inbound",
                period="2026-09",
                selected_metric_id="Booking",
            ),
        )
    )
    assert res_t1.outcome == "answer"
    assert res_t1.effective_context_label is not None
    assert "Monthly Presentation" in res_t1.effective_context_label
    assert "Inbound" in res_t1.effective_context_label
    assert "September 2026" in res_t1.effective_context_label
    assert "Booking Rate" in res_t1.effective_context_label
    assert res_t1.resolved_session_state.team == "Inbound"

    # 2. User changes page filter to Outbound -> page_context overrides stale Inbound conversation context
    res_t2 = orch.run_chat_turn(
        AiChatRequest(
            prompt="What is the team score?",
            conversation_id=res_t1.conversation_id,
            context_version=res_t1.context_version,
            session_state=res_t1.resolved_session_state,
            page_context=PageContextV1(
                page_id="team_dashboard",
                route_id="/team/outbound",
                function_id="Call Center",
                team_id="Outbound",
                period="2026-09",
            ),
        )
    )
    assert res_t2.outcome == "answer"
    assert res_t2.resolved_session_state.team == "Outbound"
    assert "Team Dashboard · Outbound" in (res_t2.effective_context_label or "")
    assert "Outbound" in res_t2.headline

    # 3. Explicit team in prompt ("Inbound") overrides PageContextV1 team_id="Outbound"
    res_t3 = orch.run_chat_turn(
        AiChatRequest(
            prompt="What is the Inbound team score in September 2026?",
            conversation_id=res_t2.conversation_id,
            context_version=res_t2.context_version,
            session_state=res_t2.resolved_session_state,
            page_context=PageContextV1(
                page_id="team_dashboard",
                route_id="/team/outbound",
                function_id="Call Center",
                team_id="Outbound",
                period="2026-09",
            ),
        )
    )
    assert res_t3.outcome == "answer"
    assert res_t3.resolved_session_state.team == "Inbound"
    assert "Inbound" in res_t3.headline


def test_page_context_pre_authorization_blocks_unauthorized_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify unauthorized team, branch, level, or employee in PageContextV1 is blocked with 0 record reads."""
    db = _build_in_memory_db()
    inb_rec = _make_inbound_record("EMP101", "Sara Mahmoud", 82.5, booking_actual=0.22)
    _patch_records(monkeypatch, [inb_rec])
    ai_evidence_cache.clear()

    # 1. Manager scoped only to Inbound Employee cannot query Outbound via PageContextV1
    inbound_mgr_scope = {
        "role": "Manager",
        "user_id": "00000000-0000-0000-0000-000000000010",
        "has_unrestricted_team_access": False,
        "accessible_functions": ["Call Center"],
        "accessible_teams": ["Inbound"],
        "accessible_team_levels": [("Inbound", "Employee")],
        "accessible_branches": ["dubai"],
    }
    res_unauth_team = PmsAiOrchestrator(db, inbound_mgr_scope).run_chat_turn(
        AiChatRequest(
            prompt="What is the score on this page?",
            page_context=PageContextV1(
                page_id="team_dashboard",
                team_id="Outbound",
                period="2026-09",
            ),
        )
    )
    assert res_unauth_team.outcome == "restricted_access"
    assert res_unauth_team.tool_calls == []
    assert "Access restricted" in res_unauth_team.headline

    # 2. Branch Director scoped only to Dubai cannot query Sharjah via PageContextV1
    res_unauth_branch = PmsAiOrchestrator(db, inbound_mgr_scope).run_chat_turn(
        AiChatRequest(
            prompt="What does this page show?",
            page_context=PageContextV1(
                page_id="monthly_presentation",
                team_id="Inbound",
                branch="sharjah",
                period="2026-09",
            ),
        )
    )
    assert res_unauth_branch.outcome == "restricted_access"
    assert res_unauth_branch.tool_calls == []
    assert "Sharjah" in res_unauth_branch.headline

    # 3. Employee self-only role cannot inspect another employee via PageContextV1
    emp_scope = {
        "role": "Employee",
        "user_id": "00000000-0000-0000-0000-000000000099",
        "employee_id": "EMP101",
        "is_self_only": True,
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Inbound"],
        "accessible_team_levels": [("Inbound", "Employee")],
    }
    res_unauth_emp = PmsAiOrchestrator(db, emp_scope).run_chat_turn(
        AiChatRequest(
            prompt="What is this employee's score?",
            page_context=PageContextV1(
                page_id="team_dashboard",
                team_id="Inbound",
                selected_entity_type="employee",
                selected_entity_id="EMP999",
            ),
        )
    )
    assert res_unauth_emp.outcome == "restricted_access"
    assert res_unauth_emp.tool_calls == []


def test_page_help_and_role_aware_navigation_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify page_help and navigation capabilities explain pages and filter destinations by role with 0 record reads."""
    db = _build_in_memory_db()
    _patch_records(monkeypatch, [])
    ai_evidence_cache.clear()

    # 1. Monthly Presentation page_help for Manager
    mgr_scope = {
        "role": "Manager",
        "user_id": "00000000-0000-0000-0000-000000000021",
        "has_unrestricted_team_access": False,
        "accessible_functions": ["Call Center"],
        "accessible_teams": ["Inbound"],
        "accessible_team_levels": [("Inbound", "Employee"), ("Inbound", "Managerial")],
    }
    help_res = PmsAiOrchestrator(db, mgr_scope).run_chat_turn(
        AiChatRequest(
            prompt="What does this page show?",
            page_context=PageContextV1(
                page_id="monthly_presentation",
                route_id="/monthly-presentation",
                function_id="Call Center",
                team_id="Inbound",
                period="2026-09",
                selected_metric_id="Booking",
            ),
        )
    )
    assert help_res.outcome == "answer"
    assert help_res.capability_mode == "page_help"
    assert help_res.tool_calls == []
    assert help_res.page_help is not None
    assert help_res.page_help.page_id == "monthly_presentation"
    assert len(help_res.page_help.key_elements) >= 2
    assert len(help_res.page_help.available_actions) >= 1
    assert help_res.page_help.metric_explanation is not None
    assert "Booking Rate" in help_res.page_help.metric_explanation

    # 2. Navigation for Function Director (read-only for uploads/settings, authorized for BSC & corrective actions view)
    dir_scope = {
        "role": "Function Director",
        "user_id": "00000000-0000-0000-0000-000000000022",
        "accessible_functions": ["Call Center"],
    }
    nav_dir = PmsAiOrchestrator(db, dir_scope).run_chat_turn(
        AiChatRequest(
            prompt="Where can I find the Balanced Scorecard and corrective actions?",
            page_context=PageContextV1(
                page_id="team_dashboard",
                team_id="Inbound",
                period="2026-09",
            ),
        )
    )
    assert nav_dir.outcome == "answer"
    assert nav_dir.capability_mode == "navigation"
    assert nav_dir.tool_calls == []
    dir_routes = {t.route for t in nav_dir.navigation_targets}
    assert any("/corrective-actions" in r or "/executive" in r for r in dir_routes)
    assert not any("/upload" in r for r in dir_routes)
    assert not any("/settings" in r for r in dir_routes)

    # 3. Navigation for Employee self-only (only own scorecard)
    emp_scope = {
        "role": "Employee",
        "user_id": "00000000-0000-0000-0000-000000000023",
        "employee_id": "EMP101",
        "is_self_only": True,
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Inbound"],
        "accessible_team_levels": [("Inbound", "Employee")],
    }
    nav_emp = PmsAiOrchestrator(db, emp_scope).run_chat_turn(
        AiChatRequest(
            prompt="How do I find my scorecard?",
            page_context=PageContextV1(
                page_id="team_dashboard",
                team_id="Inbound",
                employee_id="EMP101",
            ),
        )
    )
    assert nav_emp.outcome == "answer"
    assert nav_emp.capability_mode == "navigation"
    assert len(nav_emp.navigation_targets) == 1
    assert "/employee/EMP101" in nav_emp.navigation_targets[0].route


def test_fallback_sample_data_guardrail_blocks_analytics_and_proposals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Monthly Presentation fallback/sample data is disclosed on page_help and refused for analytics & proposals."""
    db = _build_in_memory_db()
    inb_rec = _make_inbound_record("EMP101", "Sara Mahmoud", 82.5, booking_actual=0.22)
    _patch_records(monkeypatch, [inb_rec])
    ai_evidence_cache.clear()

    mgr_scope = {
        "role": "Manager",
        "user_id": "00000000-0000-0000-0000-000000000031",
        "has_unrestricted_team_access": True,
    }
    orch = PmsAiOrchestrator(db, mgr_scope)

    fallback_ctx = PageContextV1(
        page_id="monthly_presentation",
        route_id="/monthly-presentation",
        function_id="Call Center",
        team_id="Inbound",
        period="2026-09",
        is_fallback_data=True,
    )

    # 1. page_help is allowed on fallback view but discloses sample data warning
    res_help = orch.run_chat_turn(
        AiChatRequest(prompt="What does this page show?", page_context=fallback_ctx)
    )
    assert res_help.outcome == "answer"
    assert res_help.capability_mode == "page_help"
    assert res_help.basis_warning is not None
    assert "sample" in res_help.basis_warning.casefold() or "fallback" in res_help.basis_warning.casefold()

    # 2. Analytical query on fallback view is refused (unavailable_data, 0 tool calls)
    res_query = orch.run_chat_turn(
        AiChatRequest(prompt="What is the Inbound Booking Rate?", page_context=fallback_ctx)
    )
    assert res_query.outcome == "unavailable_data"
    assert res_query.tool_calls == []
    assert res_query.action_proposal is None
    assert "sample fallback data" in res_query.headline.casefold()

    # 3. Proposal request on fallback view is refused
    res_prop = orch.run_chat_turn(
        AiChatRequest(prompt="Propose a corrective action plan for Inbound", page_context=fallback_ctx)
    )
    assert res_prop.outcome == "unavailable_data"
    assert res_prop.action_proposal is None

    # 4. Direct confirmation with is_fallback_data=True raises CorrectiveActionValidationError
    with pytest.raises(CorrectiveActionValidationError):
        confirm_corrective_action_proposal(
            db=db,
            scope=mgr_scope,
            body=AiCorrectiveActionConfirmRequest(
                proposal_id="prop-fallback-1",
                team="Inbound",
                month="September",
                year=2026,
                action_type="Coaching",
                priority="High",
                action_text="Coach team on booking conversion",
                due_date="2026-10-15",
                evidence_revision="rev1",
                is_fallback_data=True,
            ),
        )


def test_evidence_based_corrective_action_proposal_and_confirmation_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Phase 5 corrective action proposal structure, role write gating, confirmation persistence (Open status),
    and stale evidence revision conflict detection."""
    db = _build_in_memory_db()
    t_inb = Team(
        name="Inbound",
        db_name="Inbound",
        display_name="Inbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    db.add(t_inb)
    db.flush()
    db.add_all(
        [
            Employee(
                employee_id="EMP101",
                name="Sara Mahmoud",
                team_id=t_inb.id,
                region="EGY",
                performance_level="Employee",
                is_active=True,
            ),
            Employee(
                employee_id="EMP102",
                name="Radwa Ahmed",
                team_id=t_inb.id,
                region="EGY",
                performance_level="Employee",
                is_active=True,
            ),
        ]
    )
    db.commit()

    rec1 = _make_inbound_record("EMP101", "Sara Mahmoud", 78.0, booking_actual=0.20, booking_target=0.30)
    rec2 = _make_inbound_record("EMP102", "Radwa Ahmed", 81.0, booking_actual=0.24, booking_target=0.30)
    _patch_records(monkeypatch, [rec1, rec2])
    ai_evidence_cache.clear()

    # 1. Manager can generate proposal with can_user_create_action=True and persisted_status_on_save="Open"
    mgr_scope = {
        "role": "Manager",
        "user_id": "00000000-0000-0000-0000-000000000041",
        "username": "mgr_inbound",
        "has_unrestricted_team_access": False,
        "accessible_functions": ["Call Center"],
        "accessible_teams": ["Inbound"],
        "accessible_team_levels": [("Inbound", "Employee")],
    }
    res_prop_mgr = PmsAiOrchestrator(db, mgr_scope).run_chat_turn(
        AiChatRequest(
            prompt="Propose a corrective action for Booking Rate",
            page_context=PageContextV1(
                page_id="team_dashboard",
                route_id="/team/inbound",
                function_id="Call Center",
                team_id="Inbound",
                period="2026-09",
                selected_metric_id="Booking",
            ),
        )
    )
    assert res_prop_mgr.outcome == "answer"
    assert res_prop_mgr.capability_mode == "proposal"
    prop = res_prop_mgr.action_proposal
    assert prop is not None
    assert prop.can_user_create_action is True
    assert prop.persisted_status_on_save == "Open"
    assert prop.team == "Inbound"
    assert prop.metric_display_name == "Booking Rate"
    assert len(prop.observed_facts) >= 2
    assert prop.hypothesis is not None and "unverified" in prop.hypothesis.casefold()
    assert len(prop.suggested_steps) >= 2
    assert prop.success_measure
    # Must NOT have written anything to DB before explicit confirmation
    assert db.query(Action).count() == 0

    # 2. Read-only Function Director / Viewer gets proposal with can_user_create_action=False and cannot confirm
    readonly_scope = {
        "role": "Function Director",
        "user_id": "00000000-0000-0000-0000-000000000042",
        "accessible_functions": ["Call Center"],
    }
    res_prop_ro = PmsAiOrchestrator(db, readonly_scope).run_chat_turn(
        AiChatRequest(
            prompt="Propose a corrective action for Booking Rate in Inbound",
            page_context=PageContextV1(
                page_id="monthly_presentation",
                team_id="Inbound",
                period="2026-09",
                selected_metric_id="Booking",
            ),
        )
    )
    assert res_prop_ro.action_proposal is not None
    assert res_prop_ro.action_proposal.can_user_create_action is False
    assert "read-only access" in res_prop_ro.headline

    future_due = (dt.date.today() + dt.timedelta(days=14)).isoformat()

    with pytest.raises(CorrectiveActionAccessError):
        confirm_corrective_action_proposal(
            db=db,
            scope=readonly_scope,
            body=AiCorrectiveActionConfirmRequest(
                proposal_id=prop.proposal_id,
                team="Inbound",
                month=prop.month,
                year=prop.year,
                employee_id="EMP101",
                action_type=prop.action_type,
                priority=prop.priority,
                action_text=prop.proposed_action_text,
                root_cause_note=prop.proposed_root_cause_note,
                due_date=future_due,
                evidence_revision=prop.evidence_revision,
            ),
        )

    # 3. Manager confirms employee-scoped action -> creates Open action in Action table
    confirmed_emp = confirm_corrective_action_proposal(
        db=db,
        scope=mgr_scope,
        body=AiCorrectiveActionConfirmRequest(
            proposal_id=prop.proposal_id,
            team="Inbound",
            month=prop.month,
            year=prop.year,
            employee_id="EMP101",
            linked_kpi_key=prop.linked_kpi_key,
            action_type=prop.action_type,
            priority=prop.priority,
            action_text=prop.proposed_action_text,
            root_cause_note=prop.proposed_root_cause_note,
            due_date=future_due,
            evidence_revision=prop.evidence_revision,
        ),
    )
    assert confirmed_emp.persisted_status == "Open"
    assert confirmed_emp.action_scope == "employee"
    assert confirmed_emp.action.get("status") == "Open"
    assert db.query(Action).count() == 1
    saved_action = db.query(Action).first()
    assert saved_action is not None
    assert saved_action.status == "Open"

    # 4. Manager confirms team-scoped action (employee_id=None) -> creates Open team action
    confirmed_team = confirm_corrective_action_proposal(
        db=db,
        scope=mgr_scope,
        body=AiCorrectiveActionConfirmRequest(
            proposal_id=prop.proposal_id,
            team="Inbound",
            month=prop.month,
            year=prop.year,
            employee_id=None,
            action_type="Coaching",
            priority=prop.priority,
            action_text=prop.proposed_action_text,
            root_cause_note=prop.proposed_root_cause_note,
            due_date=future_due,
            evidence_revision=prop.evidence_revision,
        ),
    )
    assert confirmed_team.persisted_status == "Open"
    assert confirmed_team.action_scope == "team"
    assert db.query(Action).filter(Action.employee_id.is_(None)).count() == 1

    # 5. Bump evaluation data version -> confirming with stale evidence_revision raises ProposalStaleEvidenceError
    CacheInvalidationService.bump_data_version()
    with pytest.raises(ProposalStaleEvidenceError):
        confirm_corrective_action_proposal(
            db=db,
            scope=mgr_scope,
            body=AiCorrectiveActionConfirmRequest(
                proposal_id=prop.proposal_id,
                team="Inbound",
                month=prop.month,
                year=prop.year,
                action_type=prop.action_type,
                priority=prop.priority,
                action_text=prop.proposed_action_text,
                due_date=future_due,
                evidence_revision=prop.evidence_revision,
            ),
        )


def test_categorized_user_feedback_and_ownership(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify categorized user feedback recording and trace ownership enforcement."""
    db = _build_in_memory_db()
    _patch_records(monkeypatch, [_make_inbound_record("EMP101", "Sara Mahmoud", 88.0, booking_actual=0.29)])
    ai_evidence_cache.clear()

    scope_u1 = {
        "role": "Manager",
        "user_id": "00000000-0000-0000-0000-000000000051",
        "has_unrestricted_team_access": True,
    }
    res = PmsAiOrchestrator(db, scope_u1).run_chat_turn(
        AiChatRequest(
            prompt="What does this page show?",
            page_context=PageContextV1(page_id="monthly_presentation", team_id="Inbound", period="2026-09"),
        )
    )
    assert res.trace_id

    logger = TrainingTraceLogger(db)
    found, eligible = logger.record_feedback(
        trace_id=res.trace_id,
        rating="down",
        category="incorrect_scope",
        reason="Expected Outbound scope",
        caller_user_id="00000000-0000-0000-0000-000000000051",
    )
    assert found is True
    assert eligible is False

    # Different user cannot submit feedback on u1's trace
    with pytest.raises(TraceOwnershipError):
        logger.record_feedback(
            trace_id=res.trace_id,
            rating="up",
            category="helpful",
            caller_user_id="00000000-0000-0000-0000-000000000099",
        )


def test_intent_json_schema_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """The provider-side structured-output schema accepts exactly the allowed intents."""
    schema = build_intent_json_schema()
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert set(schema["schema"]["properties"]["intent"]["enum"]) == ALLOWED_INTENTS
    assert {"page_help", "navigation", "proposal"}.issubset(ALLOWED_INTENTS)
