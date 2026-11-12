"""Reproduction and regression tests for the 6 independent review repair areas (EGY & UAE)."""

from __future__ import annotations

from types import SimpleNamespace
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import (
    Action,
    Employee,
    EmployeeUploadBatch,
    KPIValue,
    ManagementKPIConfig,
    ManagementKPISnapshot,
    PerformanceRecord,
    Team,
    UploadLog,
    User,
    UserTeamAssignment,
)
from models.ai_schemas import (
    AiChatRequest,
    AiCorrectiveActionConfirmRequest,
    PageContextV1,
    SessionFilterContext,
    TypedMetricEvidence,
)
from services.ai.catalog import ai_evidence_cache
from services.ai.contextual_assistant import (
    CorrectiveActionValidationError,
    build_corrective_action_proposal_from_evidence,
    confirm_corrective_action_proposal,
    validate_page_context_scope,
)
from services.ai.coverage_manifest import build_coverage_manifest
from services.ai.local_data_explorer import validate_grounded_synthesis
from services.ai.orchestrator import PmsAiOrchestrator
from services.corrective_action_service import CorrectiveActionService
from services.dashboard_record_service import DashboardRecordService
from services.employee_directory_service import EmployeeDirectoryService
from services.performance_dashboard_read_service import PerformanceDashboardReadService
from utils.report_scope import (
    filter_records_by_scope,
    filter_records_by_team_levels,
    user_can_access_team_level,
)


def _make_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Team.__table__,
            EmployeeUploadBatch.__table__,
            UploadLog.__table__,
            Employee.__table__,
            PerformanceRecord.__table__,
            KPIValue.__table__,
            ManagementKPIConfig.__table__,
            ManagementKPISnapshot.__table__,
            User.__table__,
            UserTeamAssignment.__table__,
            Action.__table__,
        ],
    )
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


# ---------------------------------------------------------------------------
# 1. Restore authorization boundaries first
# ---------------------------------------------------------------------------

def test_manager_pre_approvals_op_dubai_receives_dubai_rows_only():
    """A Manager assigned Pre-Approvals OP Dubai at Employee level must receive Dubai rows only, never OP Final SHJAJM."""
    db = _make_db()
    try:
        t_dubai = Team(
            id=uuid.uuid4(),
            name="pre_approvals_op_dubai",
            db_name="Pre-Approvals OP Dubai",
            display_name="Pre-Approvals OP Dubai",
            region="UAE",
            team_level="employee",
            is_active=True,
        )
        t_shj = Team(
            id=uuid.uuid4(),
            name="pre_approvals_op_final_shj_ajm",
            db_name="Pre-Approvals OP Final SHJAJM",
            display_name="Pre-Approvals OP Final SHJAJM",
            region="UAE",
            team_level="employee",
            is_active=True,
        )
        db.add_all([t_dubai, t_shj])
        db.flush()

        e_dubai = Employee(
            id=uuid.uuid4(),
            employee_id="OP-DXB-1",
            name="Dubai OP Agent",
            team_id=t_dubai.id,
            region="UAE",
            performance_level="Employee",
            is_active=True,
        )
        e_shj = Employee(
            id=uuid.uuid4(),
            employee_id="OP-SHJ-1",
            name="Sharjah OP Agent",
            team_id=t_shj.id,
            region="UAE",
            performance_level="Employee",
            is_active=True,
        )
        db.add_all([e_dubai, e_shj])
        db.flush()

        r_dubai = PerformanceRecord(
            id=uuid.uuid4(),
            employee_id=e_dubai.id,
            team_id=t_dubai.id,
            month="September",
            year=2026,
            performance_level="Employee",
            region="UAE",
            branch_key="dubai",
            score=91.0,
            grade="B",
            status="Good",
        )
        r_shj = PerformanceRecord(
            id=uuid.uuid4(),
            employee_id=e_shj.id,
            team_id=t_shj.id,
            month="September",
            year=2026,
            performance_level="Employee",
            region="UAE",
            branch_key="sharjah",
            score=84.0,
            grade="C",
            status="Average",
        )
        db.add_all([r_dubai, r_shj])
        db.commit()

        scope = {
            "user_id": str(uuid.uuid4()),
            "role": "Manager",
            "accessible_teams": ["Pre-Approvals OP Dubai"],
            "accessible_team_levels": [("Pre-Approvals OP Dubai", "Employee")],
            "has_unrestricted_team_access": False,
            "legacy_unscoped": False,
        }

        # 1) Real SQL scope predicate via DashboardRecordService / PerformanceRepository._apply_scope
        sql_records = DashboardRecordService(db).list_records(scope=scope)
        assert [r.employee_id for r in sql_records] == ["OP-DXB-1"]

        # 2) Bounded read API service (PerformanceDashboardReadService)
        page = PerformanceDashboardReadService(db, scope).records_page(period="2026-09")
        assert [item["employee_id"] for item in page["items"]] == ["OP-DXB-1"]

        # 3) Python scope helpers
        all_rows = [
            {"team": "Pre-Approvals OP Dubai", "performance_level": "Employee", "employee_id": "OP-DXB-1"},
            {"team": "Pre-Approvals OP Final SHJAJM", "performance_level": "Employee", "employee_id": "OP-SHJ-1"},
        ]
        assert [r["employee_id"] for r in filter_records_by_scope(all_rows, scope)] == ["OP-DXB-1"]
        assert user_can_access_team_level(scope, "Pre-Approvals OP Dubai", "Employee") is True
        assert user_can_access_team_level(scope, "Pre-Approvals OP Final SHJAJM", "Employee") is False
    finally:
        db.close()


def test_manager_call_center_managerial_and_inbound_employee_cannot_update_call_center_employee():
    """A Manager with Call Center / Managerial and Inbound / Employee must retain those grants and receive 403/PermissionError on Call Center / Employee."""
    db = _make_db()
    try:
        t_cc = Team(
            id=uuid.uuid4(),
            name="call_center",
            db_name="Call Center",
            display_name="Call Center",
            region="EGY",
            team_level="employee",
            is_active=True,
        )
        t_inb = Team(
            id=uuid.uuid4(),
            name="inbound",
            db_name="Inbound",
            display_name="Inbound",
            region="EGY",
            team_level="employee",
            is_active=True,
        )
        db.add_all([t_cc, t_inb])
        db.flush()

        emp_cc_emp = Employee(
            id=uuid.uuid4(),
            employee_id="CC-EMP-1",
            name="Call Center Support Rep",
            team_id=t_cc.id,
            region="EGY",
            performance_level="Employee",
            is_active=True,
        )
        emp_cc_mgr = Employee(
            id=uuid.uuid4(),
            employee_id="CC-MGR-1",
            name="Call Center Lead",
            team_id=t_cc.id,
            region="EGY",
            performance_level="Managerial",
            is_active=True,
        )
        emp_inb_emp = Employee(
            id=uuid.uuid4(),
            employee_id="INB-EMP-1",
            name="Inbound Rep",
            team_id=t_inb.id,
            region="EGY",
            performance_level="Employee",
            is_active=True,
        )
        db.add_all([emp_cc_emp, emp_cc_mgr, emp_inb_emp])
        db.flush()

        db.add_all([
            PerformanceRecord(
                id=uuid.uuid4(),
                employee_id=emp_cc_emp.id,
                team_id=t_cc.id,
                month="September",
                year=2026,
                performance_level="Employee",
                region="EGY",
                score=78.0,
                grade="C",
                status="Average",
            ),
            PerformanceRecord(
                id=uuid.uuid4(),
                employee_id=emp_cc_mgr.id,
                team_id=t_cc.id,
                month="September",
                year=2026,
                performance_level="Managerial",
                region="EGY",
                score=88.0,
                grade="B",
                status="Good",
            ),
            PerformanceRecord(
                id=uuid.uuid4(),
                employee_id=emp_inb_emp.id,
                team_id=t_inb.id,
                month="September",
                year=2026,
                performance_level="Employee",
                region="EGY",
                score=92.0,
                grade="B",
                status="Good",
            ),
        ])
        db.commit()

        scope = {
            "user_id": str(uuid.uuid4()),
            "role": "Manager",
            "accessible_teams": ["Call Center", "Inbound"],
            "accessible_team_levels": [("Call Center", "Managerial"), ("Inbound", "Employee")],
            "has_unrestricted_team_access": False,
            "legacy_unscoped": False,
        }

        assert user_can_access_team_level(scope, "Call Center", "Managerial") is True
        assert user_can_access_team_level(scope, "Inbound", "Employee") is True
        assert user_can_access_team_level(scope, "Call Center", "Employee") is False

        # Updating Call Center / Employee via EmployeeDirectoryService must raise PermissionError (403)
        with pytest.raises(PermissionError):
            EmployeeDirectoryService(db).update("CC-EMP-1", name="Tampered Name", scope=scope)

        # Updating corrective action on Call Center / Employee must raise PermissionError (403)
        with pytest.raises(PermissionError):
            CorrectiveActionService(db).ensure_employee_scope("CC-EMP-1", scope)

        # SQL scope and Python filter must exclude Call Center / Employee while keeping Call Center / Managerial and Inbound / Employee
        sql_records = DashboardRecordService(db).list_records(scope=scope)
        assert {r.employee_id for r in sql_records} == {"CC-MGR-1", "INB-EMP-1"}

        filtered = filter_records_by_team_levels(
            [
                {"team": "Call Center", "performance_level": "Employee", "employee_id": "CC-EMP-1"},
                {"team": "Call Center", "performance_level": "Managerial", "employee_id": "CC-MGR-1"},
                {"team": "Inbound", "performance_level": "Employee", "employee_id": "INB-EMP-1"},
            ],
            scope,
        )
        assert {r["employee_id"] for r in filtered} == {"CC-MGR-1", "INB-EMP-1"}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2. Secure corrective-action confirmation
# ---------------------------------------------------------------------------

def test_corrective_action_confirmation_rejects_unissued_proposal_unknown_employee_and_duplicates():
    """Confirmation must reject unissued proposal_ids, never create Employee/Team rows, and enforce idempotency."""
    db = _make_db()
    try:
        team = Team(
            id=uuid.uuid4(),
            name="inbound",
            db_name="Inbound",
            display_name="Inbound",
            region="EGY",
            team_level="employee",
            is_active=True,
        )
        db.add(team)
        db.flush()

        emp = Employee(
            id=uuid.uuid4(),
            employee_id="INB-101",
            name="Verified Agent",
            team_id=team.id,
            region="EGY",
            performance_level="Employee",
            is_active=True,
        )
        user = User(
            id=uuid.uuid4(),
            username="mgr_inbound",
            email="mgr@test.local",
            password_hash="x",
            role="Manager",
            is_active=True,
        )
        db.add_all([emp, user])
        db.flush()

        rec = PerformanceRecord(
            id=uuid.uuid4(),
            employee_id=emp.id,
            team_id=team.id,
            month="September",
            year=2026,
            performance_level="Employee",
            region="EGY",
            score=68.0,
            grade="E",
            status="Needs Improvement",
        )
        db.add(rec)
        db.add(
            UserTeamAssignment(
                id=uuid.uuid4(),
                user_id=user.id,
                team_id=team.id,
                performance_level="Employee",
                access_level="write",
                assigned_by="Admin",
            )
        )
        db.commit()

        scope = {
            "user_id": str(user.id),
            "role": "Manager",
            "accessible_teams": ["Inbound"],
            "accessible_team_levels": [("Inbound", "Employee")],
            "has_unrestricted_team_access": False,
            "legacy_unscoped": False,
        }

        # 1) Never-issued proposal_id with unknown employee_id on an authorized team must fail and NOT create Employee or Team rows
        emp_count_before = db.query(Employee).count()
        team_count_before = db.query(Team).count()
        action_count_before = db.query(Action).count()
        from services.ai.contextual_assistant import _current_evidence_revision
        cur_rev = _current_evidence_revision(db)

        with pytest.raises(CorrectiveActionValidationError):
            confirm_corrective_action_proposal(
                db=db,
                scope=scope,
                body=AiCorrectiveActionConfirmRequest(
                    proposal_id="prop-forged-never-issued",
                    team="Inbound",
                    month="September",
                    year=2026,
                    employee_id="UNKNOWN-EMP-999",
                    action_type="Coaching",
                    action_text="Forged action",
                    evidence_revision=cur_rev,
                ),
            )

        assert db.query(Employee).count() == emp_count_before
        assert db.query(Team).count() == team_count_before
        assert db.query(Action).count() == action_count_before

        # 2) Valid issued proposal succeeds once, rejects tampered subject, and is idempotent on duplicate retry
        proposal = build_corrective_action_proposal_from_evidence(
            db=db,
            scope=scope,
            session_state=SessionFilterContext(
                team="Inbound",
                month="September",
                year=2026,
                performance_level="Employee",
                employee_id="INB-101",
            ),
            typed_evidence=[
                TypedMetricEvidence(
                    metric_id="inbound:quality_score",
                    kpi_key="quality_score",
                    display_name="Quality Score",
                    team="Inbound",
                    function="Call Center",
                    performance_level="Employee",
                    period="September 2026",
                    period_label="September 2026",
                    value_kind="rate",
                    unit="%",
                    actual=72.0,
                    actual_value=72.0,
                    actual_display="72.0%",
                    target=90.0,
                    target_value=90.0,
                    target_display="90.0%",
                    achievement_percent=80.0,
                    weight_percent=25.0,
                    contributes_to_score=True,
                    direction="higher_better",
                    sample_size=1,
                    source_link="/team/inbound",
                )
            ],
            records=[
                SimpleNamespace(
                    employee_id="INB-101",
                    employee_name="Verified Agent",
                    team="Inbound",
                    month="September",
                    year=2026,
                    evaluation=SimpleNamespace(score=68.0, grade="E"),
                )
            ],
        )
        assert proposal is not None

        # Tampering with employee_id on a valid proposal_id must be rejected
        with pytest.raises(CorrectiveActionValidationError):
            confirm_corrective_action_proposal(
                db=db,
                scope=scope,
                body=AiCorrectiveActionConfirmRequest(
                    proposal_id=proposal.proposal_id,
                    team="Inbound",
                    month="September",
                    year=2026,
                    employee_id="UNKNOWN-EMP-999",
                    action_type=proposal.action_type,
                    action_text=proposal.proposed_action_text,
                    evidence_revision=proposal.evidence_revision,
                ),
            )
        assert db.query(Employee).count() == emp_count_before
        assert db.query(Action).count() == action_count_before

        # First valid confirmation creates exactly 1 action
        valid_req = AiCorrectiveActionConfirmRequest(
            proposal_id=proposal.proposal_id,
            team="Inbound",
            month="September",
            year=2026,
            employee_id="INB-101",
            action_type=proposal.action_type,
            action_text="Conduct targeted quality coaching session.",
            root_cause_note=proposal.proposed_root_cause_note,
            priority="High",
            linked_kpi_key=proposal.linked_kpi_key,
            evidence_revision=proposal.evidence_revision,
        )
        first_res = confirm_corrective_action_proposal(db=db, scope=scope, body=valid_req)
        assert first_res.success is True
        assert db.query(Action).count() == action_count_before + 1

        # Second identical confirmation (retry) must not create a second Action row
        second_res = confirm_corrective_action_proposal(db=db, scope=scope, body=valid_req)
        assert second_res.action["id"] == first_res.action["id"]
        assert db.query(Action).count() == action_count_before + 1
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 3. Correct request binding and country-aware evidence caching
# ---------------------------------------------------------------------------

def test_country_switch_egy_80_and_uae_95_does_not_collide_in_evidence_cache(monkeypatch):
    """Switching countries (Egypt 80% vs UAE 95%) under the same authorized account must return the right country's score without clearing cache."""
    monkeypatch.setenv("PMS_AI_LOCAL_DATA_EXPLORATION_ENABLED", "false")
    db = _make_db()
    try:
        t_egy = Team(
            id=uuid.uuid4(),
            name="inbound_egy",
            db_name="Inbound",
            display_name="Inbound",
            region="EGY",
            team_level="employee",
            is_active=True,
        )
        t_uae = Team(
            id=uuid.uuid4(),
            name="inbound_uae",
            db_name="Inbound UAE",
            display_name="Inbound UAE",
            region="UAE",
            team_level="employee",
            is_active=True,
        )
        db.add_all([t_egy, t_uae])
        db.flush()

        e_egy = Employee(
            id=uuid.uuid4(),
            employee_id="EGY-INB-1",
            name="Egypt Inbound Agent",
            team_id=t_egy.id,
            region="EGY",
            performance_level="Employee",
            is_active=True,
        )
        e_uae = Employee(
            id=uuid.uuid4(),
            employee_id="UAE-INB-1",
            name="UAE Inbound Agent",
            team_id=t_uae.id,
            region="UAE",
            performance_level="Employee",
            is_active=True,
        )
        db.add_all([e_egy, e_uae])
        db.flush()

        db.add_all([
            PerformanceRecord(
                id=uuid.uuid4(),
                employee_id=e_egy.id,
                team_id=t_egy.id,
                month="September",
                year=2026,
                performance_level="Employee",
                region="EGY",
                score=80.0,
                grade="C",
                status="Meets",
            ),
            PerformanceRecord(
                id=uuid.uuid4(),
                employee_id=e_uae.id,
                team_id=t_uae.id,
                month="September",
                year=2026,
                performance_level="Employee",
                region="UAE",
                branch_key="dubai",
                score=95.0,
                grade="A",
                status="Exceeds",
            ),
        ])
        db.commit()

        ai_evidence_cache.clear()
        scope = {
            "user_id": str(uuid.uuid4()),
            "role": "Admin",
            "has_unrestricted_team_access": True,
            "legacy_unscoped": False,
        }

        orch_egy = PmsAiOrchestrator(db=db, scope=scope)
        resp_egy = orch_egy.run_chat_turn(
            AiChatRequest(
                prompt="What is the Inbound score in September 2026?",
                session_state=SessionFilterContext(region="EGY", month="September", year=2026),
            )
        )
        assert "80.0%" in resp_egy.headline

        # Now switch to UAE WITHOUT clearing ai_evidence_cache
        orch_uae = PmsAiOrchestrator(db=db, scope=scope)
        resp_uae = orch_uae.run_chat_turn(
            AiChatRequest(
                prompt="What is the Inbound score in September 2026?",
                session_state=SessionFilterContext(region="UAE", month="September", year=2026),
            )
        )
        assert "95.0%" in resp_uae.headline
    finally:
        db.close()


def test_explicit_branch_on_dubai_page_denies_dubai_only_branch_director(monkeypatch):
    """Asking about Sharjah while on a Dubai page must evaluate against Sharjah and deny a Dubai-only Branch Director."""
    monkeypatch.setenv("PMS_AI_LOCAL_DATA_EXPLORATION_ENABLED", "false")
    db = _make_db()
    try:
        scope = {
            "user_id": str(uuid.uuid4()),
            "role": "Branch Director",
            "accessible_branches": ["dubai"],
            "legacy_unscoped": False,
        }
        ctx = PageContextV1(
            surface="team_dashboard",
            page_key="team_dashboard",
            page_label="Team Dashboard",
            route="/team/inbound-uae",
            region="UAE",
            team_id="Inbound UAE",
            team_label="Inbound UAE",
            branch="dubai",
            performance_level="Employee",
            month="September",
            year=2026,
        )
        orch = PmsAiOrchestrator(db=db, scope=scope)
        resp = orch.run_chat_turn(
            AiChatRequest(
                prompt="How many bookings did Sharjah have in September 2026?",
                page_context=ctx,
            )
        )
        assert resp.outcome == "restricted_access"
        assert "sharjah" in resp.headline.lower()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 4. Validate claims, including the association between each fact and its value
# ---------------------------------------------------------------------------

def test_claim_validator_rejects_swapped_values_wrong_units_wrong_month_and_contradictory_winner():
    """validate_grounded_synthesis must verify subject-to-value binding, units, period, and comparison winner."""
    fact_ledger = [
        {
            "fact_id": "F1",
            "metric": "bookings",
            "subject": "Dubai",
            "value": 180,
            "unit": "count",
            "period": "September 2026",
        },
        {
            "fact_id": "F2",
            "metric": "bookings",
            "subject": "Sharjah",
            "value": 70,
            "unit": "count",
            "period": "September 2026",
        },
    ]

    # 1) Correct synthesis passes
    text_ok, reason = validate_grounded_synthesis(
        draft_payload={
            "fact_ids": ["F1", "F2"],
            "headline": "In September 2026, Dubai recorded 180 bookings compared with 70 in Sharjah, so Dubai led Sharjah.",
        },
        fact_ledger=fact_ledger,
    )
    assert text_ok is not None, f"Expected valid, got {reason}"

    # 2) Swapped values: Dubai 70 and Sharjah 180 -> MUST FAIL
    text_swap, _ = validate_grounded_synthesis(
        draft_payload={
            "fact_ids": ["F1", "F2"],
            "headline": "In September 2026, Dubai recorded 70 bookings and Sharjah recorded 180 bookings.",
        },
        fact_ledger=fact_ledger,
    )
    assert text_swap is None

    # 3) Counts presented as percentages -> MUST FAIL
    text_unit, _ = validate_grounded_synthesis(
        draft_payload={
            "fact_ids": ["F1", "F2"],
            "headline": "In September 2026, Dubai recorded 180% and Sharjah recorded 70%.",
        },
        fact_ledger=fact_ledger,
    )
    assert text_unit is None

    # 4) Wrong month attribution -> MUST FAIL
    text_month, _ = validate_grounded_synthesis(
        draft_payload={
            "fact_ids": ["F1", "F2"],
            "headline": "In August 2026, Dubai recorded 180 bookings and Sharjah recorded 70 bookings.",
        },
        fact_ledger=fact_ledger,
    )
    assert text_month is None

    # 5) Contradicting winner claim -> MUST FAIL
    text_winner, _ = validate_grounded_synthesis(
        draft_payload={
            "fact_ids": ["F1", "F2"],
            "headline": "In September 2026, Sharjah led Dubai with 70 bookings vs 180 bookings in Dubai.",
        },
        fact_ledger=fact_ledger,
    )
    assert text_winner is None

    # 6) Invented number when fact_ledger has no numeric evidence -> MUST FAIL
    empty_numeric_ledger = [
        {
            "fact_id": "F1",
            "metric": "status",
            "subject": "Inbound",
            "value": None,
            "unit": "",
            "period": "September 2026",
        }
    ]
    text_invented, _ = validate_grounded_synthesis(
        draft_payload={
            "fact_ids": ["F1"],
            "headline": "Inbound achieved 92.5% in September 2026.",
        },
        fact_ledger=empty_numeric_ledger,
    )
    assert text_invented is None


# ---------------------------------------------------------------------------
# 5. Dynamic coverage manifest and registered routes
# ---------------------------------------------------------------------------

def test_coverage_manifest_discovers_new_active_db_team_as_pending_and_uses_registered_routes():
    """Adding an active team with a published record in DB must appear in the manifest as PENDING (not CERTIFIED)."""
    db = _make_db()
    try:
        new_team = Team(
            id=uuid.uuid4(),
            name="telehealth_uae",
            db_name="Telehealth UAE",
            display_name="Telehealth UAE",
            region="UAE",
            team_level="employee",
            is_active=True,
        )
        db.add(new_team)
        db.flush()

        emp = Employee(
            id=uuid.uuid4(),
            employee_id="TH-UAE-1",
            name="Telehealth Coordinator",
            team_id=new_team.id,
            region="UAE",
            performance_level="Employee",
            is_active=True,
        )
        db.add(emp)
        db.flush()

        db.add(
            PerformanceRecord(
                id=uuid.uuid4(),
                employee_id=emp.id,
                team_id=new_team.id,
                month="September",
                year=2026,
                performance_level="Employee",
                region="UAE",
                score=89.0,
                grade="B",
                status="Good",
            )
        )
        db.commit()

        manifest = build_coverage_manifest(db)
        cells = manifest.get("coverage_cells") or []
        matching = [
            cell
            for cell in cells
            if (cell.get("team") or cell.get("canonical_team")) == "Telehealth UAE"
            and cell.get("performance_level") == "Employee"
        ]
        assert len(matching) == 1
        assert matching[0]["coverage_state"] in {"partial", "blocked"}
        assert matching[0].get("evidence_passes") is not True

        # Also verify no cell points to unregistered /bsc route
        for cell in cells:
            dest = str(cell.get("destination_route") or "")
            assert not dest.startswith("/bsc"), f"Found unregistered route {dest}"
    finally:
        db.close()


def test_live_grant_revocation_between_steps_and_during_synthesis_with_and_without_persistence(monkeypatch):
    """Revoking a user's DB team grant mid-turn must abort returning evidence, persistence, and trace logging."""
    from api.dependencies import build_user_scope_from_db_user
    from models.models import AiConversation, AiInteractionTrace, AiTurn
    from repositories.ai_conversation_repository import compute_scope_fingerprint

    db = _make_db()
    try:
        t_inb = Team(
            id=uuid.uuid4(),
            name="Inbound",
            db_name="Inbound",
            display_name="Inbound",
            region="EGY",
            team_level="employee",
            is_active=True,
        )
        db.add(t_inb)
        db.flush()

        emp = Employee(
            id=uuid.uuid4(),
            employee_id="INB-REV-1",
            name="Revocation Test Agent",
            team_id=t_inb.id,
            region="EGY",
            performance_level="Employee",
            is_active=True,
        )
        db.add(emp)
        db.flush()

        db.add(
            PerformanceRecord(
                id=uuid.uuid4(),
                employee_id=emp.id,
                team_id=t_inb.id,
                month="September",
                year=2026,
                performance_level="Employee",
                region="EGY",
                score=91.5,
                grade="A",
                status="Excellent",
            )
        )

        mgr_user = User(
            id=uuid.uuid4(),
            full_name="Mgr Revoke",
            username="mgr.revoke",
            email="mgr.revoke@example.com",
            password_hash="x",
            role="Manager",
            is_active=True,
            must_change_password=False,
        )
        db.add(mgr_user)
        db.flush()

        assign = UserTeamAssignment(
            user_id=mgr_user.id,
            team_id=t_inb.id,
            performance_level="Employee",
            assigned_by="system",
        )
        db.add(assign)
        db.commit()

        user_obj = db.query(User).filter(User.id == mgr_user.id).first()
        scope = build_user_scope_from_db_user(db, user_obj)

        # Revoke grant during exploration / synthesis when conversation persistence is disabled
        import services.ai.local_data_explorer as lde

        def _revoke_during_synth(**kwargs):
            db.query(UserTeamAssignment).filter(UserTeamAssignment.user_id == mgr_user.id).delete()
            db.commit()
            return ("Inbound achieved 91.5% in September 2026.", 10.0, "ok")

        def _fake_planner(**kwargs):
            step_num = kwargs.get("step", 1)
            if step_num == 1:
                return (
                    {
                        "action": "call_tools",
                        "unknown_code": "none",
                        "tools": [{"tool": "get_team_score_summary", "team": "Inbound", "period": "2026-09"}],
                    },
                    10.0,
                    "ok",
                )
            return ({"action": "finish", "unknown_code": "none", "tools": []}, 10.0, "ok")

        monkeypatch.setenv("PMS_AI_LOCAL_DATA_EXPLORATION_ENABLED", "true")
        monkeypatch.setenv("PMS_AI_LOCAL_EVIDENCE_SYNTHESIS_ENABLED", "true")
        monkeypatch.setattr(lde, "_compose_grounded_answer", _revoke_during_synth)
        monkeypatch.setattr(lde, "local_exploration_enabled", lambda: True)
        monkeypatch.setattr(lde, "_call_local_exploration_model", _fake_planner)

        orch = PmsAiOrchestrator(db=db, scope=scope)
        res_no_persist = orch.run_chat_turn(
            AiChatRequest(
                prompt="How did Inbound perform in September 2026?",
                session_state=SessionFilterContext(
                    team="Inbound",
                    month="September",
                    year=2026,
                    performance_level="Employee",
                    region="EGY",
                ),
            )
        )
        assert res_no_persist.outcome == "restricted_access"
        assert res_no_persist.typed_evidence == []
        assert "91.5" not in res_no_persist.headline
        assert db.query(AiInteractionTrace).count() == 0

        # Re-grant and test revocation with conversation persistence enabled
        db.add(
            UserTeamAssignment(
                user_id=mgr_user.id,
                team_id=t_inb.id,
                performance_level="Employee",
                assigned_by="system",
            )
        )
        db.commit()
        scope_persisted = build_user_scope_from_db_user(
            db, db.query(User).filter(User.id == mgr_user.id).first()
        )
        conv = AiConversation(
            id=str(uuid.uuid4()),
            owner_user_id=str(mgr_user.id),
            owner_role="Manager",
        )
        db.add(conv)
        db.commit()

        orch_persisted = PmsAiOrchestrator(db=db, scope=scope_persisted)
        res_persisted = orch_persisted.run_chat_turn(
            AiChatRequest(
                prompt="How did Inbound perform in September 2026?",
                conversation_id=str(conv.id),
                session_state=SessionFilterContext(
                    team="Inbound",
                    month="September",
                    year=2026,
                    performance_level="Employee",
                    region="EGY",
                ),
            )
        )
        assert res_persisted.outcome == "restricted_access"
        assert res_persisted.typed_evidence == []
        assert "91.5" not in res_persisted.headline
        assert db.query(AiInteractionTrace).count() == 0
    finally:
        db.close()
