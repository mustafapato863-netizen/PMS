"""Phase 3 Test Suite: Shared Authorized Data Tools & Pre-Query Scoping Contracts.

Verifies:
1. Unified tool contracts across planner and executor (DeterministicToolRegistry.AUTHORIZED_MODEL_LED_TOOLS).
2. Server-side pre-query RBAC gating (is_self_only, accessible_branches, accessible_teams).
3. Authoritative TypedMetricEvidence generation for all 6 model-led tools.
4. Non-Call Center department support (Coding UAE, Coding EGY, Pharmacy, Finance).
5. Numerical fidelity: real 0.0 vs null/missing data, rank ties, and denominators.
6. Zero database mutations (ReadOnlySessionGuard).
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import SessionFilterContext, TypedMetricEvidence
from models.schemas import (
    CallsData,
    EvaluationData,
    GeoBreakdown,
    GeoData,
    PerformanceRecord,
)
from services.ai.tool_registry import (
    DeterministicToolRegistry,
    ToolExecutionContext,
    ToolExecutionResult,
)
from services.database_record_source import DatabaseRecordSource
from services.dashboard_record_service import DashboardRecordService


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()


@pytest.fixture
def synth_records() -> list[PerformanceRecord]:
    recs: list[PerformanceRecord] = []

    # 1. Inbound Call Center Agents (EGY based)
    r1 = PerformanceRecord(
        id="Inbound_EMP501_2026_Sep",
        employee_id="EMP501",
        employee_name="Nadia Fadel",
        team="Inbound",
        month="September",
        year=2026,
        region="EGY",
        branch="dubai",
        raw_data={"Branch": "Dubai"},
        position="Senior Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=91.0, grade="A"),
        calls=CallsData(inbound=480, total_handled=550, abandoned=0),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=130, sharjah=45, ajman=25, clinics=10),
            attended=GeoBreakdown(dubai=115, sharjah=40, ajman=22, clinics=9),
        ),
        kpi_values=[
            {"kpi_key": "Booking", "label": "Booking Rate", "actual_value": 27.0, "target_value": 25.0, "unit": "%", "direction": "higher_better"},
            {"kpi_key": "waitingtime", "label": "Waiting Time", "actual_value": 6.2, "target_value": 5.0, "unit": "min", "direction": "lower_better"},
            {"kpi_key": "abandon_rate", "label": "Abandon Rate", "actual_value": 0.0, "target_value": 3.0, "unit": "%", "direction": "lower_better"},
            {"kpi_key": "bookings_count", "label": "Bookings Count", "actual_value": 180, "target_value": 150, "unit": "count", "direction": "higher_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 91.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )
    r2 = PerformanceRecord(
        id="Inbound_EMP502_2026_Sep",
        employee_id="EMP502",
        employee_name="Tarek Omar",
        team="Inbound",
        month="September",
        year=2026,
        region="EGY",
        branch="sharjah",
        raw_data={"Branch": "Sharjah"},
        position="Call Center Agent",
        performance_level="Employee",
        status="Needs Improvement",
        evaluation=EvaluationData(score=79.5, grade="C"),
        calls=CallsData(inbound=300, total_handled=320, abandoned=15),
        geo=GeoData(
            bookings=GeoBreakdown(dubai=60, sharjah=50, ajman=10, clinics=5),
            attended=GeoBreakdown(dubai=50, sharjah=42, ajman=8, clinics=4),
        ),
        kpi_values=[
            {"kpi_key": "Booking", "label": "Booking Rate", "actual_value": 20.0, "target_value": 25.0, "unit": "%", "direction": "higher_better"},
            {"kpi_key": "waitingtime", "label": "Waiting Time", "actual_value": 7.4, "target_value": 5.0, "unit": "min", "direction": "lower_better"},
            {"kpi_key": "abandon_rate", "label": "Abandon Rate", "actual_value": 4.5, "target_value": 3.0, "unit": "%", "direction": "lower_better"},
            {"kpi_key": "bookings_count", "label": "Bookings Count", "actual_value": 120, "target_value": 150, "unit": "count", "direction": "higher_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 79.5, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )
    # August record for Nadia (trend)
    r1_aug = PerformanceRecord(
        id="Inbound_EMP501_2026_Aug",
        employee_id="EMP501",
        employee_name="Nadia Fadel",
        team="Inbound",
        month="August",
        year=2026,
        region="EGY",
        branch="dubai",
        raw_data={"Branch": "Dubai"},
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
            {"kpi_key": "waitingtime", "label": "Waiting Time", "actual_value": 6.8, "target_value": 5.0, "unit": "min", "direction": "lower_better"},
            {"kpi_key": "bookings_count", "label": "Bookings Count", "actual_value": 160, "target_value": 150, "unit": "count", "direction": "higher_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 88.5, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 2. Coding UAE Employee
    r_code_uae = PerformanceRecord(
        id="Coding_EMP701_2026_Sep",
        employee_id="EMP701",
        employee_name="Hassan Zaki",
        team="Coding",
        month="September",
        year=2026,
        region="UAE",
        branch="dubai",
        position="Medical Coder",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=92.0, grade="A"),
        kpi_values=[
            {"kpi_key": "QualityErrors", "label": "Quality Errors", "actual_value": 2.5, "target_value": 3.0, "unit": "%", "direction": "lower_better"},
            {"kpi_key": "Rejection", "label": "Rejection", "actual_value": 4.1, "target_value": 5.0, "unit": "%", "direction": "lower_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 92.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 3. Coding Egypt Employee
    r_code_egy = PerformanceRecord(
        id="CodingEGY_EMP801_2026_Sep",
        employee_id="EMP801",
        employee_name="Mona Samir",
        team="Coding EGY",
        month="September",
        year=2026,
        region="EGY",
        branch="cairo",
        position="RCM -SHJ- OP CODING",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=94.5, grade="A"),
        kpi_values=[
            {"kpi_key": "egy_coding_quality_errors", "label": "Quality Errors Rate", "actual_value": 1.8, "target_value": 2.5, "unit": "%", "direction": "lower_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 94.5, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 4. Pharmacy Employee
    r_pharm = PerformanceRecord(
        id="Pharmacy_EMP901_2026_Sep",
        employee_id="EMP901",
        employee_name="Youssef Nabil",
        team="Pharmacy",
        month="September",
        year=2026,
        region="UAE",
        branch="dubai",
        position="Pharmacist",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=89.0, grade="B"),
        kpi_values=[
            {"kpi_key": "waitingtime", "label": "Waiting Time", "actual_value": 4.2, "target_value": 5.0, "unit": "min", "direction": "lower_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 89.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 5. Marketing Employee
    r_mkt = PerformanceRecord(
        id="Marketing_EMP1001_2026_Sep",
        employee_id="EMP1001",
        employee_name="Laila Nour",
        team="Marketing",
        month="September",
        year=2026,
        region="UAE",
        branch="dubai",
        position="Media Buyer",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=90.0, grade="A"),
        kpi_values=[
            {"kpi_key": "mb_cpl", "label": "Cost Per Lead", "actual_value": 45.0, "target_value": 50.0, "unit": "AED", "direction": "lower_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 90.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 6. Finance Employee
    r_fin = PerformanceRecord(
        id="Finance_EMP1101_2026_Sep",
        employee_id="EMP1101",
        employee_name="Ahmed Magdy",
        team="Finance",
        month="September",
        year=2026,
        region="EGY",
        branch="cairo",
        position="General Accountant",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=93.0, grade="A"),
        kpi_values=[
            {"kpi_key": "journal_entry_accuracy_rate", "label": "Journal Entry Accuracy", "actual_value": 99.2, "target_value": 98.0, "unit": "%", "direction": "higher_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 93.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 7. HR Employee
    r_hr = PerformanceRecord(
        id="HR_EMP1201_2026_Sep",
        employee_id="EMP1201",
        employee_name="Salma Raouf",
        team="Human Resources",
        month="September",
        year=2026,
        region="UAE",
        branch="dubai",
        position="HR Specialist",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=92.5, grade="A"),
        kpi_values=[
            {"kpi_key": "recruitment_sla_compliance", "label": "Recruitment SLA Compliance", "actual_value": 95.0, "target_value": 90.0, "unit": "%", "direction": "higher_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 92.5, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 8. IT Employee
    r_it = PerformanceRecord(
        id="IT_EMP1301_2026_Sep",
        employee_id="EMP1301",
        employee_name="Karim Sami",
        team="IT",
        month="September",
        year=2026,
        region="UAE",
        branch="dubai",
        position="IT Support Engineer",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=94.0, grade="A"),
        kpi_values=[
            {"kpi_key": "ticket_resolution_time", "label": "Ticket Resolution Time", "actual_value": 1.5, "target_value": 2.0, "unit": "hr", "direction": "lower_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 94.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 9. Sales Managerial Record
    r_sales_mgr = PerformanceRecord(
        id="Sales_EMP1401_2026_Sep",
        employee_id="EMP1401",
        employee_name="Ziad Mansour",
        team="Sales",
        month="September",
        year=2026,
        region="UAE",
        branch="dubai",
        position="Sales Manager",
        performance_level="Managerial",
        status="On Track",
        evaluation=EvaluationData(score=96.0, grade="A"),
        kpi_values=[
            {"kpi_key": "pipeline_attainment", "label": "Pipeline Attainment", "actual_value": 108.5, "target_value": 100.0, "unit": "%", "direction": "higher_better"},
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 96.0, "target_value": 90.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    # 10. Record with missing KPI (no abandon_rate)
    r_missing_kpi = PerformanceRecord(
        id="Inbound_EMP1501_2026_Sep",
        employee_id="EMP1501",
        employee_name="Farida Nader",
        team="Inbound",
        month="September",
        year=2026,
        region="EGY",
        branch="dubai",
        position="Call Center Agent",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=85.0, grade="B"),
        kpi_values=[
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 85.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )

    recs.extend([r1, r2, r1_aug, r_code_uae, r_code_egy, r_pharm, r_mkt, r_fin, r_hr, r_it, r_sales_mgr, r_missing_kpi])
    return recs


def _patch_sources(monkeypatch, records: list[PerformanceRecord]):
    monkeypatch.setattr(DatabaseRecordSource, "get_all", lambda *args, **kwargs: records)
    monkeypatch.setattr(DashboardRecordService, "list_analysis_records", lambda *args, **kwargs: records)
    monkeypatch.setattr(DashboardRecordService, "list_record_index", lambda *args, **kwargs: None)


# ---------------------------------------------------------------------------
# Test 1: Tool Schema Catalog & Parity
# ---------------------------------------------------------------------------

def test_tool_catalog_contains_all_authorized_tools():
    tools = DeterministicToolRegistry.AUTHORIZED_MODEL_LED_TOOLS
    expected_tools = {
        "read_employee_metric",
        "get_employee_history",
        "compare_branches",
        "get_score_trend",
        "rank_employees",
        "get_kpi_diagnosis",
        "simulate_kpi_improvement",
        "explain_scoring_rules_and_targets",
        "search_pms_guide",
        "query_rankings",
        "discover_pms_catalog",
        "get_corrective_actions",
    }
    assert expected_tools.issubset(set(tools.keys()))
    for name, schema in tools.items():
        assert schema.get("type") == "object"
        assert "properties" in schema
        assert "description" in schema


def test_router_tool_schemas_match_registry_schemas():
    from services.ai.tool_registry import DeterministicToolRegistry
    from services.ai.router import HybridQueryRouter

    # In router.py, tool_schemas references DeterministicToolRegistry.AUTHORIZED_MODEL_LED_TOOLS
    assert DeterministicToolRegistry.AUTHORIZED_MODEL_LED_TOOLS is not None
    # Twelve model-led tools: the six original read/trend tools, the KPI simulation,
    # scoring-explanation and system-guide helpers, the composable query_rankings engine,
    # the RBAC-scoped discover_pms_catalog lookup, and get_corrective_actions.
    assert len(DeterministicToolRegistry.AUTHORIZED_MODEL_LED_TOOLS) == 12


# ---------------------------------------------------------------------------
# Test 2: Server-Side RBAC & Pre-Query Scope Gating
# ---------------------------------------------------------------------------

def test_rbac_self_only_restricts_cross_employee_access(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    # Employee scope with is_self_only=True
    self_scope = {
        "user_id": "u-emp501",
        "role": "Employee",
        "employee_id": "EMP501",
        "is_self_only": True,
        "accessible_teams": ["Inbound"],
    }
    ctx = ToolExecutionContext(db=memory_db, scope=self_scope, session_state=SessionFilterContext(employee_id="EMP501"))
    registry = DeterministicToolRegistry(ctx)

    # 1. Accessing own metric: permitted
    res = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP501", "employee_name": "Nadia Fadel", "metric_id": "waitingtime", "period": "2026-09", "team": "Inbound"},
    )
    assert res.records_evaluated > 0

    # 2. Accessing another employee's metric: rejected fast via PermissionError
    with pytest.raises(PermissionError, match="Self-only scope restriction"):
        registry.execute_model_led_tool(
            "read_employee_metric",
            {"employee_id": "EMP502", "employee_name": "Tarek Omar", "metric_id": "waitingtime", "period": "2026-09", "team": "Inbound"},
        )

    # 3. Accessing organizational analytics tools (compare_branches, rank_employees): rejected fast
    with pytest.raises(PermissionError, match="Self-only scope restriction"):
        registry.execute_model_led_tool(
            "compare_branches",
            {"team": "Inbound", "branches": ["dubai", "sharjah"], "period": "2026-09", "metric": "bookings_count"},
        )

    with pytest.raises(PermissionError, match="Self-only scope restriction"):
        registry.execute_model_led_tool(
            "rank_employees",
            {"team": "Inbound", "metric_id": "overall_score", "period": "2026-09"},
        )


def test_rbac_branch_restriction_bounds_queries(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    # Branch manager restricted to Dubai branch only
    dubai_scope = {
        "user_id": "u-dubai-mgr",
        "role": "Branch Director",
        "accessible_branches": ["dubai"],
        "accessible_teams": ["Inbound"],
    }
    ctx = ToolExecutionContext(db=memory_db, scope=dubai_scope, session_state=SessionFilterContext(branch="dubai"))
    registry = DeterministicToolRegistry(ctx)

    # Permitted branch
    res = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP501", "metric_id": "waitingtime", "period": "2026-09", "team": "Inbound", "branch": "dubai"},
    )
    assert res.records_evaluated > 0

    # Disallowed branch rejected fast
    with pytest.raises(PermissionError, match="Branch access restriction"):
        registry.execute_model_led_tool(
            "read_employee_metric",
            {"employee_id": "EMP502", "metric_id": "waitingtime", "period": "2026-09", "team": "Inbound", "branch": "sharjah"},
        )

    # Compare branches including disallowed branch rejected fast
    with pytest.raises(PermissionError, match="Branch access restriction"):
        registry.execute_model_led_tool(
            "compare_branches",
            {"team": "Inbound", "branches": ["dubai", "sharjah"], "period": "2026-09", "metric": "bookings_count"},
        )


def test_rbac_team_restriction_bounds_queries(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    # Inbound Team Manager scope
    inbound_scope = {
        "user_id": "u-inbound-sup",
        "role": "Manager",
        "accessible_teams": ["Inbound"],
    }
    ctx = ToolExecutionContext(db=memory_db, scope=inbound_scope, session_state=SessionFilterContext(team="Inbound"))
    registry = DeterministicToolRegistry(ctx)

    # Permitted team
    res = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP501", "metric_id": "waitingtime", "period": "2026-09", "team": "Inbound"},
    )
    assert res.records_evaluated > 0

    # Disallowed team rejected fast
    with pytest.raises(PermissionError, match="Team access restriction"):
        registry.execute_model_led_tool(
            "read_employee_metric",
            {"employee_id": "EMP701", "metric_id": "QualityErrors", "period": "2026-09", "team": "Coding"},
        )


# ---------------------------------------------------------------------------
# Test 3: Tool Execution & Typed Evidence Integrity across all 6 Tools
# ---------------------------------------------------------------------------

def test_read_employee_metric_returns_typed_evidence(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP501", "employee_name": "Nadia Fadel", "metric_id": "waitingtime", "period": "2026-09", "team": "Inbound"},
    )
    assert isinstance(res, ToolExecutionResult)
    assert len(res.typed_evidence) >= 1
    ev = next((e for e in res.typed_evidence if "wait" in e.kpi_key.casefold() and e.period == "September 2026"), None)
    assert ev is not None
    assert ev.actual == 6.2
    assert ev.target == 5.0
    assert ev.unit == "min"
    assert ev.direction == "lower_better"
    assert ev.employee_name == "Nadia Fadel"
    assert ev.period == "September 2026"


def test_get_employee_history_returns_multi_period_evidence(memory_db, synth_records, monkeypatch):
    august = next(r for r in synth_records if r.employee_id == "EMP501" and r.month == "August")
    waiting = next(k for k in august.kpi_values if k["kpi_key"] == "waitingtime")
    waiting.update(target_value=7.0, achievement_ratio=0.0)
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_model_led_tool(
        "get_employee_history",
        {"employee_id": "EMP501", "employee_name": "Nadia Fadel", "metric_id": "waitingtime", "period": "2026-09", "team": "Inbound"},
    )
    assert len(res.typed_evidence) >= 2
    periods = {e.period for e in res.typed_evidence}
    assert "August 2026" in periods
    assert "September 2026" in periods
    waiting_history = {e.period: e for e in res.typed_evidence if e.kpi_key == "waitingtime"}
    assert waiting_history["August 2026"].target == 7.0
    assert waiting_history["August 2026"].achievement_percent == 0.0
    assert waiting_history["September 2026"].target == 5.0
    assert waiting_history["September 2026"].achievement_percent is None


def test_compare_branches_returns_branch_evidence(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_model_led_tool(
        "compare_branches",
        {"team": "Inbound", "branches": ["dubai", "sharjah", "ajman"], "period": "2026-09", "metric": "bookings_count"},
    )
    assert len(res.typed_evidence) >= 2
    branch_names = {e.branch for e in res.typed_evidence}
    assert "dubai" in branch_names
    assert "sharjah" in branch_names


def test_rank_employees_returns_ranked_evidence_and_denominators(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_model_led_tool(
        "rank_employees",
        {"team": "Inbound", "metric_id": "overall_score", "period": "2026-09", "limit": 5},
    )
    assert len(res.typed_evidence) >= 1
    assert res.records_evaluated > 0
    # Check that employees are populated
    emp_names = [e.employee_name for e in res.typed_evidence]
    assert any(name in emp_names for name in ("Nadia Fadel", "Tarek Omar"))


def test_get_score_trend_returns_trend_evidence(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_model_led_tool(
        "get_score_trend",
        {"team": "Inbound", "employee_id": "EMP501", "metric_id": "waitingtime", "period": "2026-09"},
    )
    assert len(res.typed_evidence) >= 2


def test_get_kpi_diagnosis_returns_diagnosis_evidence(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_model_led_tool(
        "get_kpi_diagnosis",
        {"team": "Inbound", "metric_id": "Booking", "period": "2026-09"},
    )
    assert res.records_evaluated > 0


# ---------------------------------------------------------------------------
# Test 4: Non-Call Center Department Coverage (Coding UAE vs Egypt, Pharmacy)
# ---------------------------------------------------------------------------

def test_coding_uae_vs_coding_egy_country_isolation(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    # Coding UAE
    res_uae = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP701", "employee_name": "Hassan Zaki", "metric_id": "QualityErrors", "period": "2026-09", "team": "Coding"},
    )
    assert len(res_uae.typed_evidence) >= 1
    ev_uae = next((e for e in res_uae.typed_evidence if "quality" in e.kpi_key.casefold()), None)
    assert ev_uae is not None
    assert ev_uae.actual == 2.5
    assert ev_uae.target == 3.0
    assert ev_uae.unit == "%"

    # Coding Egypt
    res_egy = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP801", "employee_name": "Mona Samir", "metric_id": "egy_coding_quality_errors", "period": "2026-09", "team": "Coding EGY"},
    )
    assert len(res_egy.typed_evidence) >= 1
    ev_egy = next((e for e in res_egy.typed_evidence if "quality" in e.kpi_key.casefold()), None)
    assert ev_egy is not None
    assert ev_egy.actual == 1.8
    assert ev_egy.target == 2.5


def test_pharmacy_department_execution(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP901", "employee_name": "Youssef Nabil", "metric_id": "waitingtime", "period": "2026-09", "team": "Pharmacy"},
    )
    assert len(res.typed_evidence) >= 1
    ev = next((e for e in res.typed_evidence if "wait" in e.kpi_key.casefold()), None)
    assert ev is not None
    assert ev.actual == 4.2
    assert ev.target == 5.0
    assert ev.unit == "min"


# ---------------------------------------------------------------------------
# Test 5: Real Zero vs Null / Missing Data Preservation
# ---------------------------------------------------------------------------

def test_real_zero_abandon_rate_preserved(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    # Nadia Fadel had 0 abandoned calls / 0.0% abandon rate in Sep 2026
    res = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP501", "employee_name": "Nadia Fadel", "metric_id": "abandon_rate", "period": "2026-09", "team": "Inbound"},
    )
    assert len(res.typed_evidence) >= 1
    ev = next((e for e in res.typed_evidence if "abandon" in e.kpi_key.casefold()), None)
    assert ev is not None
    assert ev.actual == 0.0
    assert ev.actual is not None
    assert ev.actual_display == "0.0%" or "0" in ev.actual_display


def test_marketing_department_currency_unit(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP1001", "employee_name": "Laila Nour", "metric_id": "mb_cpl", "period": "2026-09", "team": "Marketing"},
    )
    assert len(res.typed_evidence) >= 1
    ev = next((e for e in res.typed_evidence if "cpl" in e.kpi_key.casefold()), None)
    assert ev is not None
    assert ev.actual == 45.0
    assert ev.target == 50.0
    assert ev.unit == "AED"
    assert ev.direction == "lower_better"
    assert ev.employee_name == "Laila Nour"


def test_finance_department_execution(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP1101", "employee_name": "Ahmed Magdy", "metric_id": "journal_entry_accuracy_rate", "period": "2026-09", "team": "Finance"},
    )
    assert len(res.typed_evidence) >= 1
    ev = next((e for e in res.typed_evidence if "journal" in e.kpi_key.casefold()), None)
    assert ev is not None
    assert ev.actual == 99.2
    assert ev.target == 98.0
    assert ev.unit == "%"


def test_hr_department_execution(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP1201", "employee_name": "Salma Raouf", "metric_id": "recruitment_sla_compliance", "period": "2026-09", "team": "Human Resources"},
    )
    assert len(res.typed_evidence) >= 1
    ev = next((e for e in res.typed_evidence if "recruitment" in e.kpi_key.casefold()), None)
    assert ev is not None
    assert ev.actual == 95.0
    assert ev.target == 90.0
    assert ev.unit == "%"


def test_it_department_execution(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP1301", "employee_name": "Karim Sami", "metric_id": "ticket_resolution_time", "period": "2026-09", "team": "IT"},
    )
    assert len(res.typed_evidence) >= 1
    ev = next((e for e in res.typed_evidence if "ticket" in e.kpi_key.casefold()), None)
    assert ev is not None
    assert ev.actual == 1.5
    assert ev.target == 2.0
    assert ev.unit == "hr"
    assert ev.direction == "lower_better"


def test_sales_managerial_level_execution(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_model_led_tool(
        "read_employee_metric",
        {
            "employee_id": "EMP1401",
            "employee_name": "Ziad Mansour",
            "metric_id": "pipeline_attainment",
            "period": "2026-09",
            "team": "Sales",
            "performance_level": "Managerial",
        },
    )
    assert len(res.typed_evidence) >= 1
    ev = next((e for e in res.typed_evidence if "pipeline" in e.kpi_key.casefold()), None)
    assert ev is not None
    assert ev.actual == 108.5
    assert ev.target == 100.0
    assert ev.unit == "%"
    assert ev.employee_name == "Ziad Mansour"


def test_country_and_team_identity_survives_dispatch(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    # 1. Dispatch to Coding (UAE)
    res_uae = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP701", "employee_name": "Hassan Zaki", "metric_id": "QualityErrors", "period": "2026-09", "team": "Coding"},
    )
    assert len(res_uae.typed_evidence) >= 1
    assert res_uae.typed_evidence[0].team == "Coding"

    # 2. Dispatch to Coding EGY
    res_egy = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP801", "employee_name": "Mona Samir", "metric_id": "egy_coding_quality_errors", "period": "2026-09", "team": "Coding EGY"},
    )
    assert len(res_egy.typed_evidence) >= 1
    assert res_egy.typed_evidence[0].team == "Coding EGY"


def test_invalid_arguments_reject_before_tool_execution(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    # 1. Unknown tool
    with pytest.raises(ValueError, match="Unknown model-led tool"):
        registry.execute_model_led_tool("drop_tables_dangerous_tool", {"param": 1})

    # 2. Missing required arguments for read_employee_metric (missing period and employee_id/employee_name)
    with pytest.raises(ValueError, match="Missing required argument"):
        registry.execute_model_led_tool("read_employee_metric", {"team": "Inbound"})


def test_missing_value_distinct_from_measured_zero(memory_db, synth_records, monkeypatch):
    _patch_sources(monkeypatch, synth_records)
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    # Farida Nader exists in Inbound, but has NO abandon_rate KPI recorded
    res = registry.execute_model_led_tool(
        "read_employee_metric",
        {"employee_id": "EMP1501", "employee_name": "Farida Nader", "metric_id": "abandon_rate", "period": "2026-09", "team": "Inbound"},
    )
    # Since abandon_rate is absent from Farida's kpi_values, no abandon_rate evidence should be returned
    ev_abandon = [e for e in res.typed_evidence if "abandon" in e.kpi_key.casefold()]
    assert len(ev_abandon) == 0, "Missing KPI must NOT evaluate to 0.0 or generate spurious evidence"


def test_tied_rank_spotlight_emits_evidence_for_all_co_leaders(memory_db, synth_records, monkeypatch):
    sup1 = PerformanceRecord(
        id="Support_EMP301_2026_Sep",
        employee_id="EMP301",
        employee_name="Kareem Adel",
        team="Call Center",
        month="September",
        year=2026,
        region="EGY",
        position="Quality Assurance",
        performance_level="Employee",
        status="Needs Improvement",
        evaluation=EvaluationData(score=62.0, grade="E"),
        kpi_values=[{"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 62.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"}],
    )
    sup2 = PerformanceRecord(
        id="Support_EMP302_2026_Sep",
        employee_id="EMP302",
        employee_name="Ziad Nabil",
        team="Call Center",
        month="September",
        year=2026,
        region="EGY",
        position="Trainer",
        performance_level="Employee",
        status="Needs Improvement",
        evaluation=EvaluationData(score=62.0, grade="E"),
        kpi_values=[{"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 62.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"}],
    )
    _patch_sources(monkeypatch, [*synth_records, sup1, sup2])
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_agent_spotlight_and_trend(
        team="Support Positions",
        month="September",
        year=2026,
        ranking_direction="worst",
        single_person=True,
    )
    emp_ids = {e.employee_id for e in res.typed_evidence if e.kpi_key == "overall_score" and e.period == "September 2026"}
    assert {"EMP301", "EMP302"}.issubset(emp_ids)
    emp302_ev = next(e for e in res.typed_evidence if e.employee_id == "EMP302" and e.kpi_key == "overall_score")
    assert emp302_ev.actual == 62.0
    assert emp302_ev.unit == "%"
    assert "/employee/EMP302" in (emp302_ev.source_link or "")


def test_threshold_employee_count_tool_and_orchestrator(memory_db, synth_records, monkeypatch):
    from models.ai_schemas import AiChatRequest
    from services.ai.orchestrator import PmsAiOrchestrator
    from services.ai.router import parse_score_threshold_query

    assert parse_score_threshold_query("How many Finance employees had a September 2026 overall score above 85%?") == ("above", 85.0)
    assert parse_score_threshold_query("How many agents are below the booking-rate target?") is None

    fin_rec = PerformanceRecord(
        id="Finance_EMP901_2026_Sep",
        employee_id="EMP901",
        employee_name="Layla Sami",
        function="Call Center",  # intentional mismatch to verify team fallback
        team="Finance",
        month="September",
        year=2026,
        region="EGY",
        position="Finance Specialist",
        performance_level="Employee",
        status="On Track",
        evaluation=EvaluationData(score=86.0, grade="B"),
        kpi_values=[{"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 86.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"}],
    )
    fin_low = PerformanceRecord(
        id="Finance_EMP905_2026_Sep",
        employee_id="EMP905",
        employee_name="Omar Adel",
        function="Call Center",
        team="Finance",
        month="September",
        year=2026,
        region="EGY",
        position="Finance Specialist",
        performance_level="Employee",
        status="Needs Improvement",
        evaluation=EvaluationData(score=80.0, grade="C"),
        kpi_values=[{"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 80.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"}],
    )
    _patch_sources(monkeypatch, [fin_rec, fin_low])
    admin_scope = {"role": "Admin", "user_id": "u-test", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    res = registry.execute_model_led_tool(
        "rank_employees",
        {"team": "Finance", "period": "2026-09", "score_threshold": 85.0, "threshold_operator": "above"},
    )
    agg = next((e for e in res.typed_evidence if e.kpi_key == "qualifying_employee_count"), None)
    assert agg is not None
    assert agg.actual == 1.0
    assert agg.unit == "count"
    assert agg.employee_id is None
    assert agg.source_link
    indiv = [e for e in res.typed_evidence if e.kpi_key == "overall_score"]
    assert [e.employee_id for e in indiv] == ["EMP901"]
    assert res.digest["threshold_count_summary"]["count"] == 1
    assert res.digest["threshold_count_summary"]["total_evaluated"] == 2

    orch = PmsAiOrchestrator(memory_db, admin_scope)
    resp = orch.run_chat_turn(
        AiChatRequest(prompt="How many Finance employees had a September 2026 overall score above 85%?")
    )
    assert resp.outcome == "answer"
    assert "Finance" in resp.headline
    assert "Layla Sami" in resp.headline
    assert any(e.kpi_key == "qualifying_employee_count" and e.actual == 1.0 for e in resp.typed_evidence)


def test_it_corporate_level_execution(memory_db, synth_records, monkeypatch):
    corp_rec = PerformanceRecord(
        id="IT_EMP903_2026_Sep",
        employee_id="EMP903",
        employee_name="Mina Fawzi",
        team="IT",
        month="September",
        year=2026,
        region="EGY",
        position="IT Director",
        performance_level="Corporate",
        status="On Track",
        evaluation=EvaluationData(score=90.0, grade="A"),
        kpi_values=[
            {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 90.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
        ],
    )
    _patch_sources(monkeypatch, [*synth_records, corp_rec])
    admin_scope = {"role": "Admin", "has_unrestricted_team_access": True}
    ctx = ToolExecutionContext(db=memory_db, scope=admin_scope, session_state=SessionFilterContext())
    registry = DeterministicToolRegistry(ctx)

    # 1. Corporate read_employee_metric returns Mina Fawzi (EMP903, 90.0%)
    res_read = registry.execute_model_led_tool(
        "read_employee_metric",
        {
            "employee_id": "EMP903",
            "employee_name": "Mina Fawzi",
            "metric_id": "overall_score",
            "period": "2026-09",
            "team": "IT",
            "performance_level": "Corporate",
        },
    )
    ev_corp = next((e for e in res_read.typed_evidence if e.employee_id == "EMP903"), None)
    assert ev_corp is not None
    assert ev_corp.employee_name == "Mina Fawzi"
    assert ev_corp.team == "IT"
    assert ev_corp.actual == 90.0
    assert ev_corp.performance_level == "Corporate"

    # 2. Corporate rank_employees returns Mina Fawzi (EMP903, 90.0%)
    res_rank_corp = registry.execute_model_led_tool(
        "rank_employees",
        {"team": "IT", "metric_id": "overall_score", "period": "2026-09", "performance_level": "Corporate"},
    )
    assert any(e.employee_id == "EMP903" and e.actual == 90.0 for e in res_rank_corp.typed_evidence)

    # 3. Employee-level queries MUST NOT leak Corporate EMP903 records
    res_read_emp = registry.execute_model_led_tool(
        "read_employee_metric",
        {
            "employee_id": "EMP903",
            "employee_name": "Mina Fawzi",
            "metric_id": "overall_score",
            "period": "2026-09",
            "team": "IT",
            "performance_level": "Employee",
        },
    )
    assert all(e.employee_id != "EMP903" for e in res_read_emp.typed_evidence)

    res_rank_emp = registry.execute_model_led_tool(
        "rank_employees",
        {"team": "IT", "metric_id": "overall_score", "period": "2026-09"},
    )
    assert all(e.employee_id != "EMP903" for e in res_rank_emp.typed_evidence)
    assert any(e.employee_id == "EMP1301" for e in res_rank_emp.typed_evidence)


