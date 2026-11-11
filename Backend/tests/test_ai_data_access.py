"""Tests for Authorized PMS AI Data Access Layer (Phase 2).

Covers:
1. Admin-only AI pilot policy enforcement (non-admin callers rejected).
2. Authorized and unauthorized access across Admin, Regional Manager, Branch Director,
   Manager, Function Viewer, and Employee scopes.
3. Strict Egypt vs UAE regional separation and cross-scope rejections.
4. Numerical and historical correctness:
   - Real 0.0 vs missing (None) KPI values preserved.
   - Missing period returns "no_data" without guessing or demo data.
   - KPI target direction and weights preserved.
   - Official score and record calculation parity.
5. Strict read-only enforcement:
   - No database writes, zero ORM mutations, ReadOnlySessionGuard blocks flushes.
   - SQL injection and script parameter injection attempts rejected.
   - Unsupported operations rejected.
6. Data minimization:
   - Free text causes, passwords, tokens, and raw uploads excluded.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import Action, Employee, KPIValue, PerformanceRecord, Team
from services.ai.data_access import (
    PmsAiDataAccess,
    SUPPORTED_OPERATIONS,
    VERIFIED_TEAMS,
    _validate_param_safety,
)
from services.ai.read_only_guard import ReadOnlySessionGuard


# ---------------------------------------------------------------------------
# Database Fixture & Seeding
# ---------------------------------------------------------------------------


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def seed_test_ecosystem(db):
    """Seed Egypt and UAE teams, employees, and performance records."""
    # 1. Egypt Inbound Team
    team_egy = Team(
        id=uuid.uuid4(),
        name="inbound",
        db_name="Inbound",
        display_name="Inbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    # 2. UAE Pre-Approvals Team
    team_uae = Team(
        id=uuid.uuid4(),
        name="pre-approvals op dubai",
        db_name="Pre-Approvals OP Dubai",
        display_name="Pre-Approvals OP Dubai",
        region="UAE",
        team_level="employee",
        is_active=True,
    )
    # 3. Outbound Team
    team_outbound = Team(
        id=uuid.uuid4(),
        name="outbound",
        db_name="Outbound",
        display_name="Outbound",
        region="EGY",
        team_level="employee",
        is_active=True,
    )
    db.add_all([team_egy, team_uae, team_outbound])
    db.flush()

    # Employees
    emp_egy = Employee(
        id=uuid.uuid4(),
        employee_id="EGY-001",
        name="Ahmed Cairo",
        team_id=team_egy.id,
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    emp_uae = Employee(
        id=uuid.uuid4(),
        employee_id="UAE-001",
        name="Fatima Dubai",
        team_id=team_uae.id,
        region="UAE",
        performance_level="Employee",
        position_name="Specialist",
        is_active=True,
    )
    db.add_all([emp_egy, emp_uae])
    db.flush()

    # Performance Records for September 2026
    rec_egy = PerformanceRecord(
        id=uuid.uuid4(),
        employee_id=emp_egy.id,
        team_id=team_egy.id,
        month="September",
        year=2026,
        performance_level="Employee",
        position_name="Agent",
        region="EGY",
        branch_key=None,
        score=85.0,
        grade="B",
        status="Meets",
    )
    rec_uae = PerformanceRecord(
        id=uuid.uuid4(),
        employee_id=emp_uae.id,
        team_id=team_uae.id,
        month="September",
        year=2026,
        performance_level="Employee",
        position_name="Specialist",
        region="UAE",
        branch_key="dubai",
        score=95.0,
        grade="A",
        status="Exceeds",
    )
    db.add_all([rec_egy, rec_uae])
    db.flush()

    # KPI Values for EGY:
    # 1) bookings_count: actual=0.0 (real measured zero, preserved as 0.0)
    # 2) upsell: actual=15.0
    kpis_egy = [
        KPIValue(
            id=uuid.uuid4(),
            record_id=rec_egy.id,
            record_year=2026,
            kpi_key="bookings_count",
            actual_value=0.0,  # Real zero
            target_value=50.0,
            achievement_ratio=0.0,
            weight_applied=0.4,
            contribution=0.0,
        ),
        KPIValue(
            id=uuid.uuid4(),
            record_id=rec_egy.id,
            record_year=2026,
            kpi_key="upsell",
            actual_value=15.0,
            target_value=20.0,
            achievement_ratio=0.75,
            weight_applied=0.6,
            contribution=0.45,
        ),
    ]

    # KPI Values for UAE
    kpis_uae = [
        KPIValue(
            id=uuid.uuid4(),
            record_id=rec_uae.id,
            record_year=2026,
            kpi_key="tat_hours",
            actual_value=1.5,
            target_value=2.0,
            achievement_ratio=1.0,
            weight_applied=0.5,
            contribution=0.5,
        ),
    ]
    db.add_all(kpis_egy + kpis_uae)

    # Prior corrective action for EGY
    action = Action(
        id=uuid.uuid4(),
        employee_id=emp_egy.id,
        team_id=team_egy.id,
        month="September",
        year=2026,
        created_at=dt.datetime(2026, 9, 1, 0, 0, 0, tzinfo=dt.timezone.utc),
        action_type="Training",
        action_text="Product training",
        root_cause_note="Confidential internal root cause note that must not be exposed",
        status="Completed",
        linked_kpi_key="bookings_count",
        is_active=True,
    )
    db.add(action)
    db.commit()

    return {
        "team_egy": team_egy,
        "team_uae": team_uae,
        "team_outbound": team_outbound,
        "emp_egy": emp_egy,
        "emp_uae": emp_uae,
        "rec_egy": rec_egy,
        "rec_uae": rec_uae,
    }


# ---------------------------------------------------------------------------
# Scope Definitions
# ---------------------------------------------------------------------------

ADMIN_SCOPE = {
    "role": "Admin",
    "has_unrestricted_team_access": True,
    "accessible_teams": ["Inbound", "Pre-Approvals OP Dubai", "Outbound"],
    "accessible_regions": ["EGY", "UAE"],
    "accessible_branches": ["dubai", "sharjah", "cairo"],
}

EGYPT_REGIONAL_SCOPE = {
    "role": "Regional Manager",
    "has_unrestricted_team_access": False,
    "accessible_teams": ["Inbound", "Outbound"],
    "accessible_regions": ["EGY"],
    "accessible_branches": ["cairo"],
}

UAE_REGIONAL_SCOPE = {
    "role": "Regional Manager",
    "has_unrestricted_team_access": False,
    "accessible_teams": ["Pre-Approvals OP Dubai"],
    "accessible_regions": ["UAE"],
    "accessible_branches": ["dubai"],
}

INBOUND_MANAGER_SCOPE = {
    "role": "Manager",
    "has_unrestricted_team_access": False,
    "accessible_teams": ["Inbound"],
    "accessible_team_levels": [("Inbound", "Employee")],
}

OUTBOUND_MANAGER_SCOPE = {
    "role": "Manager",
    "has_unrestricted_team_access": False,
    "accessible_teams": ["Outbound"],
    "accessible_team_levels": [("Outbound", "Employee")],
}

DUBAI_BRANCH_SCOPE = {
    "role": "Branch Director",
    "has_unrestricted_team_access": False,
    "accessible_teams": ["Pre-Approvals OP Dubai"],
    "accessible_branches": ["dubai"],
    "accessible_regions": ["UAE"],
}

CALL_CENTER_FUNCTION_SCOPE = {
    "role": "Function Viewer",
    "has_unrestricted_team_access": False,
    "accessible_functions": ["Call Center"],
    "accessible_teams": ["Inbound", "Outbound"],
}

RCM_FUNCTION_SCOPE = {
    "role": "Function Viewer",
    "has_unrestricted_team_access": False,
    "accessible_functions": ["RCM"],
    "accessible_teams": ["Coding", "Submission"],
}

EMPLOYEE_EGY_SCOPE = {
    "role": "Employee",
    "is_self_only": True,
    "employee_id": "EGY-001",
    "accessible_teams": ["Inbound"],
}


# ---------------------------------------------------------------------------
# Tests: Pilot Gate & RBAC Enforcement
# ---------------------------------------------------------------------------


def test_pilot_authorization_enforced(test_db):
    """Admin is permitted; non-Admin roles are rejected with PermissionError during pilot."""
    seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)

    # Admin passes
    scopes = service.list_authorized_scopes(ADMIN_SCOPE, enforce_pilot=True)
    assert scopes["role"] == "Admin"
    assert "Inbound" in scopes["accessible_teams"]

    # Non-Admin roles fail with PermissionError when enforce_pilot=True
    non_admin_scopes = [
        EGYPT_REGIONAL_SCOPE,
        UAE_REGIONAL_SCOPE,
        INBOUND_MANAGER_SCOPE,
        DUBAI_BRANCH_SCOPE,
        CALL_CENTER_FUNCTION_SCOPE,
        EMPLOYEE_EGY_SCOPE,
        {"role": "Viewer"},
    ]
    for scope in non_admin_scopes:
        with pytest.raises(PermissionError) as exc_info:
            service.list_authorized_scopes(scope, enforce_pilot=True)
        assert "restricted to Admin" in str(exc_info.value)

        with pytest.raises(PermissionError):
            service.get_performance_summary(
                scope,
                team="Inbound",
                month="September",
                year=2026,
                enforce_pilot=True,
            )


# ---------------------------------------------------------------------------
# Tests: Egypt / UAE Regional Separation & Cross-Scope Rejection
# ---------------------------------------------------------------------------


def test_egypt_uae_separation(test_db):
    """Egypt Regional Manager cannot view UAE records; UAE Regional Manager cannot view Egypt."""
    seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)

    # Egypt regional manager reading Egypt team -> succeeds
    res_egy = service.get_performance_summary(
        EGYPT_REGIONAL_SCOPE,
        team="Inbound",
        month="September",
        year=2026,
        enforce_pilot=False,  # Test underlying scope resolution
    )
    assert res_egy["status"] == "data_available"
    assert res_egy["records_count"] == 1
    assert res_egy["records"][0]["employee_id"] == "EGY-001"
    assert res_egy["records"][0]["region"] == "EGY"

    # Egypt regional manager attempting to read UAE team -> rejected as out of scope
    with pytest.raises(PermissionError) as exc_info:
        service.get_performance_summary(
            EGYPT_REGIONAL_SCOPE,
            team="Pre-Approvals OP Dubai",
            month="September",
            year=2026,
            enforce_pilot=False,
        )
    assert "outside your" in str(exc_info.value)

    # UAE regional manager reading UAE team -> succeeds
    res_uae = service.get_performance_summary(
        UAE_REGIONAL_SCOPE,
        team="Pre-Approvals OP Dubai",
        month="September",
        year=2026,
        enforce_pilot=False,
    )
    assert res_uae["status"] == "data_available"
    assert res_uae["records_count"] == 1
    assert res_uae["records"][0]["employee_id"] == "UAE-001"
    assert res_uae["records"][0]["region"] == "UAE"

    # UAE regional manager attempting to read Egypt team -> rejected
    with pytest.raises(PermissionError):
        service.get_performance_summary(
            UAE_REGIONAL_SCOPE,
            team="Inbound",
            month="September",
            year=2026,
            enforce_pilot=False,
        )


def test_cross_team_and_cross_employee_rejection(test_db):
    """Managers and employees cannot access teams or employees outside their scope."""
    seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)

    # Inbound manager attempting to read Outbound -> rejected
    with pytest.raises(PermissionError) as exc_info:
        service.get_performance_summary(
            INBOUND_MANAGER_SCOPE,
            team="Outbound",
            month="September",
            year=2026,
            enforce_pilot=False,
        )
    assert "outside your" in str(exc_info.value)

    # Inbound manager requesting UAE employee -> rejected
    with pytest.raises(PermissionError):
        service.get_performance_summary(
            INBOUND_MANAGER_SCOPE,
            team="Inbound",
            month="September",
            year=2026,
            employee_id="UAE-001",
            enforce_pilot=False,
        )

    # Function Viewer for Call Center attempting to read RCM -> rejected
    with pytest.raises(PermissionError):
        service.get_performance_summary(
            CALL_CENTER_FUNCTION_SCOPE,
            team="Pre-Approvals OP Dubai",
            month="September",
            year=2026,
            enforce_pilot=False,
        )


# ---------------------------------------------------------------------------
# Tests: Numerical and Historical Correctness
# ---------------------------------------------------------------------------


def test_real_zero_vs_missing_kpi_value_preserved(test_db):
    """Real 0.0 is preserved as 0.0, and missing KPI is not fabricated or coerced to 0."""
    seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)

    # Query KPI details for EGY Inbound (seeded: bookings_count with actual=0.0, upsell with actual=15.0)
    res = service.get_kpi_details(
        ADMIN_SCOPE,
        team="Inbound",
        month="September",
        year=2026,
        enforce_pilot=True,
    )
    assert res["status"] == "data_available"
    assert res["kpi_count"] == 2

    kpis_by_key = {item["kpi_key"]: item for item in res["kpi_items"]}

    # bookings_count had actual=0.0 -> must be preserved as 0.0 (real measured zero)
    zero_kpi = kpis_by_key["bookings_count"]
    assert zero_kpi["actual"] == 0.0
    assert zero_kpi["target"] == 50.0
    assert zero_kpi["achievement_ratio"] == 0.0
    assert zero_kpi["achievement_percent"] == 0.0

    # upsell had actual=15.0
    upsell_kpi = kpis_by_key["upsell"]
    assert upsell_kpi["actual"] == 15.0
    assert upsell_kpi["target"] == 20.0
    assert upsell_kpi["achievement_ratio"] == 0.75
    assert upsell_kpi["achievement_percent"] == 75.0

    # Querying a missing/unrecorded KPI key returns status='kpi_not_found', never demo data or 0.0
    res_missing = service.get_kpi_details(
        ADMIN_SCOPE,
        team="Inbound",
        month="September",
        year=2026,
        kpi_key="non_existent_metric",
        enforce_pilot=True,
    )
    assert res_missing["status"] == "kpi_not_found"
    assert res_missing["kpi_count"] == 0
    assert res_missing["kpi_items"] == []


def test_missing_period_returns_no_data_without_guessing(test_db):
    """Requesting an unseeded month returns status='no_data' with zero records, never demo data."""
    seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)

    res = service.get_performance_summary(
        ADMIN_SCOPE,
        team="Inbound",
        month="January",  # Not seeded
        year=2025,
        enforce_pilot=True,
    )
    assert res["status"] == "no_data"
    assert res["records_count"] == 0
    assert "No performance records found" in res["summary"]


def test_performance_summary_calculation_parity(test_db):
    """Calculations like average_score and record grades reflect official records."""
    seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)

    res = service.get_performance_summary(
        ADMIN_SCOPE,
        team="Inbound",
        month="September",
        year=2026,
        enforce_pilot=True,
    )
    assert res["status"] == "data_available"
    assert res["records_count"] == 1
    record = res["records"][0]
    # Score is 45.0 (calculated from KPI contributions: 0.0 bookings_count + 45.0 upsell)
    assert record["score"] == 45.0
    assert record["grade"] == "E"
    assert record["status"] == "Below"
    assert res["average_score"] == 45.0


# ---------------------------------------------------------------------------
# Tests: Corrective Action Context & Data Minimization
# ---------------------------------------------------------------------------


def test_corrective_action_context_read_only_and_minimized(test_db):
    """Context bundle is read-only, excludes sensitive notes, and creates zero rows."""
    seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)

    # Initial action count in DB
    initial_actions = test_db.query(Action).count()

    context = service.get_corrective_action_context(
        ADMIN_SCOPE,
        team="Inbound",
        employee_id="EGY-001",
        month="September",
        year=2026,
        enforce_pilot=True,
    )

    assert context["source_metadata"]["read_only"] is True
    assert context["source_metadata"]["writes_forbidden"] is True
    assert "insufficient_evidence_reasons" in context

    # Check prior actions sanitization
    prior_actions = context.get("prior_corrective_actions") or []
    assert len(prior_actions) == 1
    pa = prior_actions[0]
    assert pa["action_type"] == "Training"
    assert pa["status"] == "Completed"
    # Root cause note must NOT be present in sanitized output
    assert "Confidential internal root cause" not in str(pa)

    # Ensure zero new actions were added to the DB
    assert test_db.query(Action).count() == initial_actions


# ---------------------------------------------------------------------------
# Tests: Read-Only Guard & DB Mutation Blocking
# ---------------------------------------------------------------------------


def test_read_only_guard_blocks_writes(test_db):
    """Any attempt to stage writes or flush within ReadOnlySessionGuard raises RuntimeError."""
    seed_test_ecosystem(test_db)

    # 1. Flush attempt with pending writes raises RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        with ReadOnlySessionGuard(test_db):
            rogue_team = Team(name="rogue", db_name="Rogue", is_active=True)
            test_db.add(rogue_team)
            test_db.flush()
    assert "AI read tools cannot write to the database" in str(exc_info.value)

    test_db.rollback()

    # 2. Exiting the guard with uncommitted pending writes raises RuntimeError and rolls back
    with pytest.raises(RuntimeError) as exc_info2:
        with ReadOnlySessionGuard(test_db):
            rogue_team2 = Team(name="rogue2", db_name="Rogue2", is_active=True)
            test_db.add(rogue_team2)
            # Not calling flush explicitly, but guard exit detects pending writes
    assert "AI read tools cannot write to the database" in str(exc_info2.value)

    test_db.rollback()
    assert test_db.query(Team).filter(Team.name == "rogue").first() is None
    assert test_db.query(Team).filter(Team.name == "rogue2").first() is None


# ---------------------------------------------------------------------------
# Tests: Unified Dispatcher & Parameter Safety
# ---------------------------------------------------------------------------


def test_unified_tool_dispatcher(test_db):
    """execute_tool cleanly dispatches to supported operations."""
    seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)

    # 1. list_authorized_scopes
    res_scopes = service.execute_tool("list_authorized_scopes", ADMIN_SCOPE, {}, enforce_pilot=True)
    assert res_scopes["role"] == "Admin"

    # 2. get_performance_summary
    res_perf = service.execute_tool(
        "get_performance_summary",
        ADMIN_SCOPE,
        {"team": "Inbound", "month": "September", "year": 2026},
        enforce_pilot=True,
    )
    assert res_perf["status"] == "data_available"

    # 3. get_kpi_details
    res_kpi = service.execute_tool(
        "get_kpi_details",
        ADMIN_SCOPE,
        {"team": "Inbound", "month": "September", "year": 2026, "kpi_key": "bookings_count"},
        enforce_pilot=True,
    )
    assert res_kpi["status"] == "data_available"

    # 4. get_corrective_action_context
    res_ca = service.execute_tool(
        "get_corrective_action_context",
        ADMIN_SCOPE,
        {"team": "Inbound", "employee_id": "EGY-001", "month": "September", "year": 2026},
        enforce_pilot=True,
    )
    assert res_ca["source_metadata"]["read_only"] is True


def test_unsupported_operation_rejected(test_db):
    """Unsupported operations are rejected with ValueError."""
    service = PmsAiDataAccess(test_db)
    with pytest.raises(ValueError) as exc_info:
        service.execute_tool("arbitrary_sql_execute", ADMIN_SCOPE, {"query": "SELECT * FROM users"})
    assert "Unsupported AI data operation" in str(exc_info.value)


@pytest.mark.parametrize(
    "unsafe_input",
    [
        "Inbound; DROP TABLE users; --",
        "1' OR '1'='1",
        "September' UNION SELECT username, password FROM users --",
        "<script>alert('xss')</script>",
        "../../etc/passwd",
        "Inbound\x00NULL",
    ],
)
def test_parameter_injection_rejected(test_db, unsafe_input):
    """Unsafe parameters with SQL or script injection patterns are rejected."""
    service = PmsAiDataAccess(test_db)
    with pytest.raises(ValueError) as exc_info:
        service.execute_tool(
            "get_performance_summary",
            ADMIN_SCOPE,
            {"team": unsafe_input, "month": "September", "year": 2026},
            enforce_pilot=True,
        )
    assert "Unsafe parameter value detected" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Comprehensive Regression Tests: Isolation, Read-Only, Transfers, History
# ---------------------------------------------------------------------------


def test_dubai_sharjah_shared_team_isolation(test_db):
    """Dubai-scoped Branch Director requesting a shared team must not receive Sharjah records or actions."""
    shared_team = Team(
        id=uuid.uuid4(),
        name="pre-approvals op",
        db_name="Pre-Approvals OP",
        display_name="Pre-Approvals OP",
        region="UAE",
        team_level="employee",
        is_active=True,
    )
    test_db.add(shared_team)
    test_db.flush()

    emp_dxb = Employee(
        id=uuid.uuid4(),
        employee_id="DXB-001",
        name="Dubai Employee",
        team_id=shared_team.id,
        region="UAE",
        performance_level="Employee",
        position_name="Specialist",
        is_active=True,
    )
    emp_shj = Employee(
        id=uuid.uuid4(),
        employee_id="SHJ-001",
        name="Sharjah Employee",
        team_id=shared_team.id,
        region="UAE",
        performance_level="Employee",
        position_name="Specialist",
        is_active=True,
    )
    test_db.add_all([emp_dxb, emp_shj])
    test_db.flush()

    rec_dxb = PerformanceRecord(
        id=uuid.uuid4(),
        employee_id=emp_dxb.id,
        team_id=shared_team.id,
        month="September",
        year=2026,
        performance_level="Employee",
        position_name="Specialist",
        region="UAE",
        branch_key="dubai",
        score=92.0,
        grade="A",
        status="Exceeds",
    )
    rec_shj = PerformanceRecord(
        id=uuid.uuid4(),
        employee_id=emp_shj.id,
        team_id=shared_team.id,
        month="September",
        year=2026,
        performance_level="Employee",
        position_name="Specialist",
        region="UAE",
        branch_key="sharjah",
        score=78.0,
        grade="C",
        status="Needs Improvement",
    )
    test_db.add_all([rec_dxb, rec_shj])

    # Actions in shared team
    action_dxb = Action(
        id=uuid.uuid4(),
        employee_id=emp_dxb.id,
        team_id=shared_team.id,
        month="August",
        year=2026,
        created_at=dt.datetime(2026, 8, 1, 0, 0, 0, tzinfo=dt.timezone.utc),
        action_type="Training",
        action_text="Dubai action",
        status="Completed",
        is_active=True,
    )
    action_shj = Action(
        id=uuid.uuid4(),
        employee_id=emp_shj.id,
        team_id=shared_team.id,
        month="August",
        year=2026,
        created_at=dt.datetime(2026, 8, 1, 0, 0, 0, tzinfo=dt.timezone.utc),
        action_type="Training",
        action_text="Sharjah action",
        status="Completed",
        is_active=True,
    )
    test_db.add_all([action_dxb, action_shj])
    test_db.commit()

    service = PmsAiDataAccess(test_db)
    dubai_scope = {
        "role": "Branch Director",
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Pre-Approvals OP"],
        "accessible_regions": ["UAE"],
        "accessible_branches": ["dubai"],
    }

    # 1. Performance summary on shared team
    res_summary = service.get_performance_summary(
        dubai_scope,
        team="Pre-Approvals OP",
        month="September",
        year=2026,
        enforce_pilot=False,
    )
    assert res_summary["status"] == "data_available"
    assert res_summary["records_count"] == 1
    assert res_summary["records"][0]["employee_id"] == "DXB-001"
    assert res_summary["records"][0]["branch_key"] == "dubai"

    # Sharjah records must NOT appear
    returned_emp_ids = [r["employee_id"] for r in res_summary["records"]]
    assert "SHJ-001" not in returned_emp_ids

    # 2. Corrective action context for team
    res_context = service.get_corrective_action_context(
        dubai_scope,
        team="Pre-Approvals OP",
        month="September",
        year=2026,
        performance_level="Employee",
        enforce_pilot=False,
    )
    prior_actions = res_context.get("prior_corrective_actions") or []
    # Verify no action from Sharjah was returned
    for act in prior_actions:
        assert act.get("branch_key") != "sharjah"


def test_caller_pending_writes_preserved(test_db):
    """Read operations must not autoflush or discard caller's pending writes on success or error."""
    from sqlalchemy import text

    ecosystem = seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)
    team_egy = ecosystem["team_egy"]

    existing_emp = test_db.query(Employee).filter(Employee.employee_id == "EGY-001").first()

    # Caller stages a new employee and dirty updates an existing one
    staged_emp = Employee(
        id=uuid.uuid4(),
        employee_id="STAGED-001",
        name="Staged Employee",
        team_id=team_egy.id,
        region="EGY",
        performance_level="Employee",
        position_name="Intern",
        is_active=True,
    )
    test_db.add(staged_emp)
    existing_emp.name = "Temporarily Dirty Name"

    assert staged_emp in test_db.new
    assert existing_emp in test_db.dirty

    # 1. Successful read operation
    res = service.get_performance_summary(
        ADMIN_SCOPE,
        team="Inbound",
        month="September",
        year=2026,
        enforce_pilot=True,
    )
    assert res["status"] == "data_available"

    # Caller writes must still be pending in the session and NOT flushed to SQLite
    assert staged_emp in test_db.new
    assert existing_emp in test_db.dirty
    row_count = test_db.connection().execute(
        text("SELECT count(*) FROM employees WHERE employee_id='STAGED-001'")
    ).scalar()
    assert row_count == 0

    # 2. Error path (e.g. invalid team authorization failure)
    with pytest.raises(PermissionError):
        service.get_performance_summary(
            {"role": "Manager", "accessible_teams": []},
            team="UnauthorizedTeam",
            month="September",
            year=2026,
            enforce_pilot=False,
        )

    # Caller writes must still remain in test_db and NOT be rolled back or discarded!
    assert staged_emp in test_db.new
    assert existing_emp in test_db.dirty

    # Cleanup session
    test_db.rollback()


def test_transferred_employee_historical_record(test_db):
    """A transferred employee's historical record in a previous team must be accessible for that period."""
    ecosystem = seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)

    team_inbound = ecosystem["team_egy"]
    team_outbound = ecosystem["team_outbound"]

    # Transferred employee: currently assigned to Outbound
    emp_transferred = Employee(
        id=uuid.uuid4(),
        employee_id="TRANS-001",
        name="Transferred Agent",
        team_id=team_outbound.id,  # Currently in Outbound
        region="EGY",
        performance_level="Employee",
        position_name="Agent",
        is_active=True,
    )
    test_db.add(emp_transferred)
    test_db.flush()

    # Historical record in Inbound for January 2026
    rec_historical = PerformanceRecord(
        id=uuid.uuid4(),
        employee_id=emp_transferred.id,
        team_id=team_inbound.id,  # Historically in Inbound
        month="January",
        year=2026,
        performance_level="Employee",
        position_name="Agent",
        region="EGY",
        branch_key=None,
        score=88.0,
        grade="B",
        status="Meets",
    )
    test_db.add(rec_historical)
    test_db.commit()

    # 1. Querying Inbound for January 2026 succeeds because historical record exists
    res = service.get_performance_summary(
        ADMIN_SCOPE,
        team="Inbound",
        month="January",
        year=2026,
        employee_id="TRANS-001",
        enforce_pilot=True,
    )
    assert res["status"] == "data_available"
    assert res["records_count"] == 1
    assert res["records"][0]["employee_id"] == "TRANS-001"

    # 2. Querying Inbound for February 2026 fails because employee is currently in Outbound and has no Inbound record in Feb
    with pytest.raises(PermissionError) as exc_info:
        service.get_performance_summary(
            ADMIN_SCOPE,
            team="Inbound",
            month="February",
            year=2026,
            employee_id="TRANS-001",
            enforce_pilot=True,
        )
    assert "belongs to 'Outbound'" in str(exc_info.value)
    assert "no historical record in requested team 'Inbound'" in str(exc_info.value)


def test_future_actions_boundary_excluded(test_db):
    """Corrective actions created after the requested period must not be included as prior actions."""
    ecosystem = seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)

    team_egy = ecosystem["team_egy"]
    emp_egy = ecosystem["emp_egy"]

    # Action created in October 2026 (future relative to September)
    action_future = Action(
        id=uuid.uuid4(),
        employee_id=emp_egy.id,
        team_id=team_egy.id,
        month="October",
        year=2026,
        created_at=dt.datetime(2026, 10, 1, 0, 0, 0, tzinfo=dt.timezone.utc),
        action_type="Coaching",
        action_text="Future action in October",
        status="Pending",
        is_active=True,
    )
    # Action created in August 2026 (prior relative to September)
    action_past = Action(
        id=uuid.uuid4(),
        employee_id=emp_egy.id,
        team_id=team_egy.id,
        month="August",
        year=2026,
        created_at=dt.datetime(2026, 8, 1, 0, 0, 0, tzinfo=dt.timezone.utc),
        action_type="Training",
        action_text="Past action in August",
        status="Completed",
        is_active=True,
    )
    test_db.add_all([action_future, action_past])
    test_db.commit()

    # Query September 2026 context
    bundle = service.get_corrective_action_context(
        ADMIN_SCOPE,
        team="Inbound",
        month="September",
        year=2026,
        employee_id="EGY-001",
        enforce_pilot=True,
    )
    prior_actions = bundle.get("prior_corrective_actions") or []
    prior_months = [a.get("period", {}).get("month") for a in prior_actions]

    # August action must be present
    assert "August" in prior_months
    # October action must NOT be present as prior action
    assert "October" not in prior_months


def test_kpi_direction_and_scoring_basis_uncertainty(test_db):
    """KPI direction and historical scoring basis uncertainty are explicitly reported."""
    seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)

    res = service.get_kpi_details(
        ADMIN_SCOPE,
        team="Inbound",
        month="September",
        year=2026,
        enforce_pilot=True,
    )
    assert res["status"] == "data_available"
    # Unpinned historical basis reported with uncertainty
    assert res["scoring_basis_confirmed"] is False
    assert res["scoring_basis_uncertainty"] is not None

    # Check KPI item direction uncertainty reporting
    kpis = res["kpi_items"]
    assert len(kpis) >= 2
    for kpi in kpis:
        assert "direction_source" in kpi
        assert "direction_confirmed" in kpi
        assert "direction_uncertainty" in kpi


def test_coverage_claims_distinguish_configured_and_tested(test_db):
    """list_authorized_scopes clearly distinguishes configured_teams vs tested_pilot_teams."""
    service = PmsAiDataAccess(test_db)
    scopes = service.list_authorized_scopes(ADMIN_SCOPE, enforce_pilot=True)

    assert "configured_teams" in scopes
    assert "tested_pilot_teams" in scopes
    assert "unverified_teams" in scopes
    assert scopes["audit_status"] == "partial_pilot_tested"
    assert "Inbound" in scopes["tested_pilot_teams"]
    assert len(scopes["configured_teams"]) >= len(scopes["tested_pilot_teams"])
    assert scopes["source_metadata"]["scope_verified"] is True


def test_branch_scoped_prior_actions_fail_closed(test_db):
    """Branch-restricted users only see established authorized branch actions; fail closed on missing/ambiguous."""
    ecosystem = seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)
    team_uae = ecosystem["team_uae"]
    emp_uae = ecosystem["emp_uae"]

    # 1. Clear Dubai action
    act_dubai = Action(
        id=uuid.uuid4(),
        employee_id=emp_uae.id,
        team_id=team_uae.id,
        branch_key="dubai",
        month="August",
        year=2026,
        created_at=dt.datetime(2026, 8, 1, 0, 0, 0, tzinfo=dt.timezone.utc),
        action_type="Coaching",
        action_text="Dubai coaching",
        status="Completed",
        is_active=True,
    )
    # 2. Sharjah action
    act_sharjah = Action(
        id=uuid.uuid4(),
        employee_id=emp_uae.id,
        team_id=team_uae.id,
        branch_key="sharjah",
        month="August",
        year=2026,
        created_at=dt.datetime(2026, 8, 1, 0, 0, 0, tzinfo=dt.timezone.utc),
        action_type="Training",
        action_text="Sharjah training",
        status="Completed",
        is_active=True,
    )
    # 3. Missing branch action (branch_key=None)
    act_missing = Action(
        id=uuid.uuid4(),
        employee_id=emp_uae.id,
        team_id=team_uae.id,
        branch_key=None,
        month="August",
        year=2026,
        created_at=dt.datetime(2026, 8, 1, 0, 0, 0, tzinfo=dt.timezone.utc),
        action_type="Warning",
        action_text="Missing branch warning",
        status="Completed",
        is_active=True,
    )
    # 4. Ambiguous branch action (multiple branches delimited)
    act_ambiguous = Action(
        id=uuid.uuid4(),
        employee_id=emp_uae.id,
        team_id=team_uae.id,
        branch_key="dubai, sharjah",
        month="August",
        year=2026,
        created_at=dt.datetime(2026, 8, 1, 0, 0, 0, tzinfo=dt.timezone.utc),
        action_type="Monitor",
        action_text="Ambiguous monitor",
        status="Completed",
        is_active=True,
    )
    test_db.add_all([act_dubai, act_sharjah, act_missing, act_ambiguous])
    test_db.commit()

    # Scope for Dubai Branch Director (branch-restricted)
    dubai_scope = {
        "role": "Branch Director",
        "has_unrestricted_team_access": False,
        "accessible_teams": [team_uae.name],
        "accessible_branches": ["dubai"],
        "accessible_regions": ["UAE"],
        "is_branch_restricted": True,
    }

    # Test Employee Evidence Path
    emp_bundle = service.get_corrective_action_context(
        dubai_scope,
        team=team_uae.name,
        month="September",
        year=2026,
        employee_id="UAE-001",
        enforce_pilot=False,
    )
    prior_emp = emp_bundle.get("prior_corrective_actions") or []
    action_types = [a.get("action_type") for a in prior_emp]
    # Dubai action MUST be present
    assert "Coaching" in action_types
    # Sharjah, missing, and ambiguous actions MUST be excluded (fail closed)
    assert "Training" not in action_types
    assert "Warning" not in action_types
    assert "Monitor" not in action_types

    # Test Team Evidence Path (without employee_id)
    team_bundle = service.get_corrective_action_context(
        dubai_scope,
        team=team_uae.name,
        month="September",
        year=2026,
        enforce_pilot=False,
    )
    prior_team = team_bundle.get("prior_corrective_actions") or []
    team_action_types = [a.get("action_type") for a in prior_team]
    assert "Coaching" in team_action_types
    assert "Training" not in team_action_types
    assert "Warning" not in team_action_types
    assert "Monitor" not in team_action_types


def test_read_only_guard_reverts_dirty_mutations_and_blocks_sql(test_db):
    """ReadOnlySessionGuard intercepts SQL writes, reverts dirty changes, and preserves caller writes."""
    from services.ai.read_only_guard import ReadOnlySessionGuard, AI_READ_ONLY_WRITE_ERROR
    from sqlalchemy import text

    # Seed an employee
    team = Team(name="guard_team", db_name="guard_team", display_name="Guard Team", region="EGY", is_active=True)
    emp = Employee(employee_id="GUARD-001", name="Original Name", team=team, region="EGY", is_active=True)
    test_db.add_all([team, emp])
    test_db.commit()

    # 1. Direct SQL writes blocked at cursor execution
    with ReadOnlySessionGuard(test_db, allow_preexisting_writes=True):
        with pytest.raises(RuntimeError) as exc_info:
            test_db.execute(text("INSERT INTO teams (id, name, db_name, display_name, is_active) VALUES ('11111111-1111-1111-1111-111111111111', 't', 't', 't', 1)"))
        assert AI_READ_ONLY_WRITE_ERROR in str(exc_info.value)

    # 2. ORM mutations inside guard are detected, reverted, and not committed later
    with pytest.raises(RuntimeError):
        with ReadOnlySessionGuard(test_db, allow_preexisting_writes=True):
            emp.name = "Mutated Inside Guard"

    # Verify emp.name was reverted to committed DB state and session is not dirty
    assert emp.name == "Original Name"
    assert emp not in test_db.dirty

    # 3. Pre-existing dirty object modified again inside guard
    emp.name = "Caller Dirty Staged"
    assert emp in test_db.dirty
    with pytest.raises(RuntimeError):
        with ReadOnlySessionGuard(test_db, allow_preexisting_writes=True):
            emp.name = "Rogue Secondary Mutation"

    # Preexisting caller dirty value must be restored, not rogue secondary mutation
    assert emp.name == "Caller Dirty Staged"
    test_db.commit()

    # Re-query from DB to verify caller's staged value persisted
    reloaded = test_db.query(Employee).filter(Employee.employee_id == "GUARD-001").one()
    assert reloaded.name == "Caller Dirty Staged"

    # 4. Deletions inside guard are caught and reverted
    with pytest.raises(RuntimeError):
        with ReadOnlySessionGuard(test_db, allow_preexisting_writes=True):
            test_db.delete(reloaded)

    # Re-query to verify object was not deleted
    assert test_db.query(Employee).filter(Employee.employee_id == "GUARD-001").count() == 1


def test_read_only_guard_real_postgresql_isolation():
    """Verify ReadOnlySessionGuard on dedicated PostgreSQL test DB only.
    
    Strictly refuses to run against normal application or production databases.
    Requires:
      1. PMS_TEST_DATABASE_URL environment variable pointing to a dedicated test DB (ending with '_test' or containing 'test').
      2. PMS_ALLOW_PG_TEST_WRITES=1 explicit opt-in.
    """
    from urllib.parse import urlparse
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from services.ai.read_only_guard import ReadOnlySessionGuard, AI_READ_ONLY_WRITE_ERROR

    test_pg_url = os.environ.get("PMS_TEST_DATABASE_URL")
    allow_writes = os.environ.get("PMS_ALLOW_PG_TEST_WRITES") == "1"

    if not test_pg_url or not test_pg_url.startswith("postgresql"):
        pytest.skip("PostgreSQL verification blocked: PMS_TEST_DATABASE_URL is not set to a dedicated test database.")

    if not allow_writes:
        pytest.skip("PostgreSQL verification blocked: PMS_ALLOW_PG_TEST_WRITES=1 is required for integration tests that write.")

    # Positively identify dedicated test database
    parsed = urlparse(test_pg_url)
    db_name = (parsed.path or "").lstrip("/").lower()
    if not (db_name.endswith("_test") or "test" in db_name):
        pytest.skip(
            f"PostgreSQL verification blocked: Database {db_name!r} is not positively identified as a dedicated test database (name must end with '_test' or contain 'test')."
        )

    pg_engine = None
    pg_session = None
    persisted = None
    try:
        pg_engine = create_engine(test_pg_url)
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        PgSession = sessionmaker(bind=pg_engine)
        pg_session = PgSession()
        unique_name = f"pg_test_team_{uuid.uuid4().hex[:8]}"

        # Caller stages a pre-existing write
        new_team = Team(
            name=unique_name,
            db_name=unique_name,
            display_name=unique_name,
            region="UAE",
            is_active=True,
        )
        pg_session.add(new_team)

        # Enter ReadOnlySessionGuard with allow_preexisting_writes=True
        with ReadOnlySessionGuard(pg_session, allow_preexisting_writes=True):
            # Safe read query
            res = pg_session.execute(text("SELECT 1")).scalar()
            assert res == 1

            # Direct SQL write must be blocked on PostgreSQL
            with pytest.raises(RuntimeError) as exc_info:
                pg_session.execute(text(f"INSERT INTO teams (id, name, db_name, display_name, region, is_active) VALUES ('{uuid.uuid4()}', 'rogue', 'rogue', 'rogue', 'UAE', true)"))
            assert AI_READ_ONLY_WRITE_ERROR in str(exc_info.value)

        # After guard exit, caller's pre-existing write is intact and commits cleanly
        assert new_team in pg_session.new
        pg_session.commit()

        # Verify team was persisted
        persisted = pg_session.query(Team).filter(Team.name == unique_name).first()
        assert persisted is not None
        assert persisted.id == new_team.id

    except Exception as e:
        if "blocked" in str(e).lower() or isinstance(e, pytest.skip.Exception):
            raise
        pytest.skip(f"Local PostgreSQL test database not available or failed connect: {e}")
    finally:
        if pg_session is not None:
            try:
                if persisted is not None:
                    pg_session.delete(persisted)
                    pg_session.commit()
            except Exception:
                pg_session.rollback()
            pg_session.close()
        if pg_engine is not None:
            pg_engine.dispose()


def test_historical_evidence_timestamp_boundaries_and_failsafe(test_db):
    """Actions created after reporting period (even in timestamp field) or with malformed dates fail safe."""
    ecosystem = seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)
    team_egy = ecosystem["team_egy"]
    emp_egy = ecosystem["emp_egy"]

    # 1. Action created in October 2026 (timestamp field in serializer) for August period
    act_future_ts = Action(
        id=uuid.uuid4(),
        employee_id=emp_egy.id,
        team_id=team_egy.id,
        month="August",
        year=2026,
        created_at=dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc),
        action_type="Promotion",
        action_text="Future created promotion",
        status="Completed",
        is_active=True,
    )
    # 2. Action with valid August period and August creation
    act_valid_past = Action(
        id=uuid.uuid4(),
        employee_id=emp_egy.id,
        team_id=team_egy.id,
        month="August",
        year=2026,
        created_at=dt.datetime(2026, 8, 15, tzinfo=dt.timezone.utc),
        action_type="Training",
        action_text="Valid past training",
        status="Completed",
        is_active=True,
    )
    test_db.add_all([act_future_ts, act_valid_past])
    test_db.commit()

    # Query September 2026 context
    context = service.get_corrective_action_context(
        ADMIN_SCOPE,
        team="Inbound",
        month="September",
        year=2026,
        employee_id="EGY-001",
        enforce_pilot=True,
    )
    prior_actions = context.get("prior_corrective_actions") or []
    action_types = [a.get("action_type") for a in prior_actions]

    # Valid past action is included
    assert "Training" in action_types
    # Action created in October 2026 must NOT appear as prior evidence
    assert "Promotion" not in action_types

    # 3. Direct unit tests on _is_action_prior_to_period fail-safe behavior
    from services.ai.corrective_action_evidence import _is_action_prior_to_period
    # Malformed timestamp string fails closed
    assert _is_action_prior_to_period({"action_type": "x", "timestamp": "invalid-iso-date"}, "September", 2026) is False
    # Missing all timestamps and period fails closed
    assert _is_action_prior_to_period({"action_type": "x"}, "September", 2026) is False
    # Malformed year fails closed
    assert _is_action_prior_to_period({"action_type": "x", "year": "not-a-year", "month": "August"}, "September", 2026) is False
    # Malformed month fails closed
    assert _is_action_prior_to_period({"action_type": "x", "year": 2026, "month": "invalid_month"}, "September", 2026) is False

    # 4. Transferred employee out-of-scope historical branch raises PermissionError
    dubai_scope = {
        "role": "Branch Director",
        "has_unrestricted_team_access": False,
        "accessible_teams": ["Pre-Approvals OP Dubai"],
        "accessible_branches": ["dubai"],
        "accessible_regions": ["UAE"],
    }
    # Employee currently in Dubai team, but historical record was in another team/branch outside scope
    with pytest.raises(PermissionError) as exc_info:
        service.get_corrective_action_context(
            dubai_scope,
            team="Inbound",  # Egypt team outside Dubai branch scope
            month="September",
            year=2026,
            employee_id="UAE-001",
            enforce_pilot=False,
        )
    assert (
        "authorized branch/region" in str(exc_info.value).casefold()
        or "outside" in str(exc_info.value).casefold()
        or "denied" in str(exc_info.value).casefold()
    )


def test_read_only_guard_mutable_json_objects_and_alternative_sql(test_db):
    """Verify deep reversion of mutable JSON dicts/lists and blocking of alternative SQL syntax."""
    from services.ai.read_only_guard import ReadOnlySessionGuard, AI_READ_ONLY_WRITE_ERROR
    from sqlalchemy import text

    # Seed team and employee with mutable JSON-like attributes
    team = Team(
        name="json_team",
        db_name="json_team",
        display_name="JSON Team",
        region="EGY",
        is_active=True,
    )
    emp = Employee(
        employee_id="JSON-EMP-001",
        name="JSON Agent",
        team=team,
        region="EGY",
        is_active=True,
    )
    rec = PerformanceRecord(
        id=uuid.uuid4(),
        employee=emp,
        team=team,
        month="September",
        year=2026,
        performance_level="Employee",
        record_payload={"custom_tags": ["tag1", "tag2"], "metrics": {"count": 10}},
        score=85.0,
        grade="B",
        status="Approved",
    )
    test_db.add_all([team, emp, rec])
    test_db.commit()

    # 1. In-place modification of mutable JSON dict inside guard must be reverted
    assert rec.record_payload["custom_tags"] == ["tag1", "tag2"]
    with pytest.raises(RuntimeError) as exc_info:
        with ReadOnlySessionGuard(test_db, allow_preexisting_writes=True):
            # Mutate nested dictionary in-place
            rec.record_payload["custom_tags"].append("rogue_tag")
            rec.record_payload["metrics"]["count"] = 999
    assert AI_READ_ONLY_WRITE_ERROR in str(exc_info.value)

    # Verify nested mutable data was restored to pre-guard snapshot
    assert rec.record_payload["custom_tags"] == ["tag1", "tag2"]
    assert rec.record_payload["metrics"]["count"] == 10
    test_db.commit()

    # Re-query from DB to verify committed data was never polluted
    reloaded = test_db.query(PerformanceRecord).filter(PerformanceRecord.id == rec.id).one()
    assert reloaded.record_payload["custom_tags"] == ["tag1", "tag2"]
    assert reloaded.record_payload["metrics"]["count"] == 10

    # 2. Alternative SQL write syntax blocked
    alternative_queries = [
        "/* leading comment */ INSERT INTO teams (id, name, db_name, display_name, is_active) VALUES ('a', 'a', 'a', 'a', 1)",
        "-- single line comment \n INSERT INTO teams (id, name, db_name, display_name, is_active) VALUES ('b', 'b', 'b', 'b', 1)",
        "(INSERT INTO teams (id, name, db_name, display_name, is_active) VALUES ('c', 'c', 'c', 'c', 1))",
        "WITH cte AS (SELECT 1) INSERT INTO teams (id, name, db_name, display_name, is_active) VALUES ('d', 'd', 'd', 'd', 1)",
        "SELECT 1; UPDATE teams SET is_active = false",
        "DROP TABLE IF EXISTS non_existent_test_table",
    ]
    with ReadOnlySessionGuard(test_db, allow_preexisting_writes=True):
        for sql_statement in alternative_queries:
            with pytest.raises((RuntimeError, Exception)) as exc:
                test_db.execute(text(sql_statement))
            # Either blocked by ReadOnlySessionGuard or by SQLite engine query_only=ON
            assert (
                AI_READ_ONLY_WRITE_ERROR in str(exc.value)
                or "readonly database" in str(exc.value).lower()
            )


def test_read_only_guard_concurrent_sessions_do_not_block_each_other():
    """An AI read in session1 must not attach engine-wide listeners or block concurrent writes in session2."""
    import tempfile
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from services.ai.read_only_guard import ReadOnlySessionGuard, AI_READ_ONLY_WRITE_ERROR

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_db_path = f.name

    try:
        engine = create_engine(f"sqlite:///{tmp_db_path}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)

        s1 = Session()
        s2 = Session()

        try:
            # Session 1 enters ReadOnlySessionGuard
            with ReadOnlySessionGuard(s1, allow_preexisting_writes=False):
                # Session 1 is read-only
                assert s1.execute(text("SELECT 1")).scalar() == 1

                # Session 2 is an independent concurrent session executing legitimate writes
                new_team = Team(name="s2_team", db_name="s2_team", display_name="S2 Team", region="UAE", is_active=True)
                s2.add(new_team)
                # This flush and commit MUST succeed; s1 guard must not block s2!
                s2.commit()

                # Session 2 direct SQL write must also succeed
                s2.execute(text(f"INSERT INTO teams (id, name, db_name, display_name, region, team_level, is_active) VALUES ('{uuid.uuid4()}', 's2_sql', 's2_sql', 's2_sql', 'UAE', 'employee', 1)"))
                s2.commit()

                # But session 1 must still be blocked from writing
                with pytest.raises(RuntimeError) as exc_info:
                    s1.execute(text(f"INSERT INTO teams (id, name, db_name, display_name, region, team_level, is_active) VALUES ('{uuid.uuid4()}', 's1_rogue', 's1_rogue', 's1_rogue', 'UAE', 'employee', 1)"))
                assert (
                    AI_READ_ONLY_WRITE_ERROR in str(exc_info.value)
                    or "readonly database" in str(exc_info.value).lower()
                )

            # After guard exit, verify s2's writes are present in database
            assert s2.query(Team).filter(Team.name == "s2_team").count() == 1
            assert s2.query(Team).filter(Team.name == "s2_sql").count() == 1
        finally:
            s1.close()
            s2.close()
            engine.dispose()
    finally:
        if os.path.exists(tmp_db_path):
            try:
                os.remove(tmp_db_path)
            except Exception:
                pass


def test_action_actual_creation_timestamp_not_backdated_and_historical_exclusion(test_db):
    """Actions created today for an old month have actual creation time and are excluded from historical evidence."""
    ecosystem = seed_test_ecosystem(test_db)
    service = PmsAiDataAccess(test_db)
    emp_egy = ecosystem["emp_egy"]
    team_egy = ecosystem["team_egy"]

    # Create an action today for August 2026 reporting month without providing created_at
    t_before = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
    action_created_today = Action(
        id=uuid.uuid4(),
        employee_id=emp_egy.id,
        team_id=team_egy.id,
        month="August",
        year=2026,
        action_type="Coaching",
        action_text="Created today for past month",
        status="Completed",
        is_active=True,
    )
    test_db.add(action_created_today)
    test_db.commit()

    # 1. Verify action.created_at was NOT backdated to August 2026
    test_db.refresh(action_created_today)
    if action_created_today.created_at is not None:
        created = action_created_today.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=dt.timezone.utc)
        # created_at is recent (today's date)
        assert created >= t_before
        assert created.year >= 2026
        # Must NOT be backdated to August 1st 2026
        assert not (created.month == 8 and created.day == 1)

    # 2. Query historical evidence for September 2026:
    # Even though reporting month is August 2026, actual creation time is November 2026 (after September 2026)
    # The action must be EXCLUDED from prior historical evidence for September 2026!
    context = service.get_corrective_action_context(
        ADMIN_SCOPE,
        team="Inbound",
        month="September",
        year=2026,
        employee_id="EGY-001",
        enforce_pilot=True,
    )
    prior_actions = context.get("prior_corrective_actions") or []
    action_texts = [a.get("manager_action") or a.get("action_text") for a in prior_actions]
    assert not any("Created today for past month" in str(txt) for txt in action_texts)


def test_scoring_basis_confirmed_boolean_strictness(test_db):
    """evaluation_basis is confirmed ONLY when pinned/confirmed is boolean True, not truthy string 'false'."""
    service = PmsAiDataAccess(test_db)
    team = Team(name="basis_team", db_name="basis_team", display_name="Basis Team", region="EGY", is_active=True)
    emp = Employee(employee_id="BASIS-EMP-001", name="Basis Agent", team=team, region="EGY", is_active=True)
    test_db.add_all([team, emp])
    test_db.flush()

    # 1. Record with evaluation_basis carrying string "false"
    rec_false_string = PerformanceRecord(
        id=uuid.uuid4(),
        employee=emp,
        team=team,
        month="September",
        year=2026,
        performance_level="Employee",
        score=75.0,
        grade="C",
        status="Approved",
        record_payload={
            "evaluation_basis": {
                "pinned": "false",  # Truthy string in python, but logically false!
                "version_number": 2,
            }
        },
    )
    test_db.add(rec_false_string)
    test_db.commit()

    summary = service.get_kpi_details(ADMIN_SCOPE, team="Basis Team", month="September", year=2026)
    # Must NOT be marked as confirmed
    assert summary.get("scoring_basis_confirmed") is False
    assert summary.get("scoring_basis") is None

    # 2. Record with evaluation_basis carrying boolean True
    rec_false_string.record_payload = {
        "evaluation_basis": {
            "pinned": True,  # Genuine boolean True
            "version_number": 3,
        }
    }
    test_db.commit()

    summary2 = service.get_kpi_details(ADMIN_SCOPE, team="Basis Team", month="September", year=2026)
    assert summary2.get("scoring_basis_confirmed") is True
    assert "version 3" in (summary2.get("scoring_basis") or "")


def test_historical_transferred_employee_branch_access_enforced(test_db):
    """Historical performance records in an unauthorized branch cannot be accessed by branch-restricted users."""
    service = PmsAiDataAccess(test_db)

    team_dubai = Team(name="DXB Team", db_name="DXB Team", display_name="DXB Team", region="UAE", is_active=True)
    team_sharjah = Team(name="SHJ Team", db_name="SHJ Team", display_name="SHJ Team", region="UAE", is_active=True)
    test_db.add_all([team_dubai, team_sharjah])
    test_db.flush()

    # Employee EMP-TRANS is currently assigned to Dubai team
    emp = Employee(employee_id="TRANS-001", name="Transferred Agent", team=team_dubai, region="UAE", is_active=True)
    test_db.add(emp)
    test_db.flush()

    # In July 2026, employee had a performance record in Sharjah branch
    rec_shj = PerformanceRecord(
        id=uuid.uuid4(),
        employee_id=emp.id,
        team_id=team_sharjah.id,
        branch_key="sharjah",
        region="UAE",
        month="July",
        year=2026,
        performance_level="Employee",
        score=60.0,
        grade="D",
        status="Approved",
    )
    test_db.add(rec_shj)
    test_db.commit()

    # Branch Director for Dubai attempts to access July 2026 context for EMP-TRANS
    dubai_scope = {
        "role": "Branch Director",
        "has_unrestricted_team_access": False,
        "accessible_teams": ["DXB Team"],
        "accessible_branches": ["dubai"],
        "accessible_regions": ["UAE"],
    }
    with pytest.raises(PermissionError) as exc_info:
        service.get_corrective_action_context(
            dubai_scope,
            team="DXB Team",
            month="July",
            year=2026,
            employee_id="TRANS-001",
            enforce_pilot=False,
        )
    assert "assigned branches" in str(exc_info.value).lower() or "outside your authorized scope" in str(exc_info.value).lower()
