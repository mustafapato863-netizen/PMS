from __future__ import annotations

from types import SimpleNamespace
import pytest

from services.ai.catalog import (
    CAPABILITY_EVIDENCE_REGISTRY,
    get_capability_evidence,
    check_scope_data_availability,
    get_ai_catalog,
)
from services.ai.orchestrator import PmsAiOrchestrator
from models.ai_schemas import AiChatRequest, SessionFilterContext
from tests.test_ai_booking_comparisons import _build_test_db_session


def test_1_unknown_or_newly_added_team_defaults_to_blocked():
    """Any (country, function, team, level, operation) tuple not explicitly listed is blocked."""
    ev = get_capability_evidence(
        country="EGY",
        function="Radiology",
        team="MRI Specialists",
        performance_level="Employee",
        operation_family="operational_summary",
    )
    assert ev.state == "blocked"
    assert ev.evidence_ref == "none"
    assert "missing, unknown, ambiguous" in ev.known_limitations


def test_2_verifying_operational_summary_leaves_branch_comparison_blocked():
    """A team verified for one operation is not verified for all operations."""
    # Outbound has only application-test evidence for operational_summary.
    ev_summary = get_capability_evidence(
        country="EGY",
        function="Call Center",
        team="Outbound",
        performance_level="Employee",
        operation_family="operational_summary",
    )
    assert ev_summary.state == "partial"

    # Outbound has NOT been verified for branch_comparison
    ev_branches = get_capability_evidence(
        country="EGY",
        function="Call Center",
        team="Outbound",
        performance_level="Employee",
        operation_family="branch_comparison",
    )
    assert ev_branches.state == "blocked"


def test_3_verifying_egypt_team_leaves_uae_team_blocked():
    """Verification for Egypt does not imply verification for UAE."""
    # Resubmission in Egypt has partial evidence mappings
    ev_egy = get_capability_evidence(
        country="EGY",
        function="RCM",
        team="Resubmission",
        performance_level="Employee",
        operation_family="operational_summary",
    )
    assert ev_egy.state == "partial"

    # Re-Submission in UAE has its own calculation and is blocked for this operation
    ev_uae = get_capability_evidence(
        country="UAE",
        function="RCM",
        team="Re-Submission",
        performance_level="Employee",
        operation_family="operational_summary",
    )
    assert ev_uae.state == "blocked"


def test_4_verifying_employee_leaves_managerial_blocked():
    """Verification for Employee does not imply verification for Managerial or Corporate."""
    # Inbound Employee has application-test evidence, pending independent parity.
    ev_emp = get_capability_evidence(
        country="EGY",
        function="Call Center",
        team="Inbound",
        performance_level="Employee",
        operation_family="operational_summary",
    )
    assert ev_emp.state == "partial"

    # Inbound Managerial is blocked
    ev_mgr = get_capability_evidence(
        country="EGY",
        function="Call Center",
        team="Inbound",
        performance_level="Managerial",
        operation_family="operational_summary",
    )
    assert ev_mgr.state == "blocked"


def test_5_missing_or_mismatched_scope_dimensions_never_inherit_a_match():
    assert get_capability_evidence(
        team="Inbound",
        operation_family="operational_summary",
    ).state == "blocked"
    assert get_capability_evidence(
        country="EGY",
        function="RCM",
        team="Inbound",
        performance_level="Employee",
        operation_family="operational_summary",
    ).state == "blocked"
    assert get_capability_evidence(
        country="EGY",
        function="Call Center",
        team="Inbound",
        performance_level="Employee",
    ).state == "blocked"
    assert get_capability_evidence(
        country="EGY",
        function="Call Center",
        team="Inbound",
        operation_family="operational_summary",
    ).state == "blocked"


def test_6_country_and_team_aliases_resolve_only_with_explicit_country():
    aliased = get_capability_evidence(
        country="Egypt",
        function="Contact Center",
        team="inbound agents",
        performance_level="employee",
        operation_family="operational_summary",
    )
    assert aliased.state == "partial"
    assert aliased.team == "Inbound"

    egypt_coding = get_capability_evidence(
        country="EGY",
        function="Revenue Cycle Management",
        team="Coding",
        performance_level="Employee",
        operation_family="operational_summary",
    )
    assert egypt_coding.state == "partial"
    assert egypt_coding.team == "Coding EGY"

    assert get_capability_evidence(
        country=None,
        function="RCM",
        team="Coding",
        performance_level="Employee",
        operation_family="operational_summary",
    ).state == "blocked"


def test_7_no_scope_is_certified_without_independent_source_parity_evidence():
    assert all(entry.state != "verified" for entry in CAPABILITY_EVIDENCE_REGISTRY)
    assert all(
        "independent source-parity evidence is pending" in entry.known_limitations
        for entry in CAPABILITY_EVIDENCE_REGISTRY
        if entry.evidence_ref.startswith("Backend/tests/")
    )


def test_8_dynamic_data_availability_september_vs_october():
    """Dynamic availability correctly reports data present for a team in September even if October has no data."""
    rec_sep = SimpleNamespace(
        month="September",
        year=2026,
        team="Coding",
        region="EGY",
        employee=SimpleNamespace(team="Coding"),
    )
    records = [rec_sep]

    # Query September -> has_data is True
    res_sep = check_scope_data_availability(
        records,
        country="EGY",
        team="Coding",
        month="September",
        year=2026,
    )
    assert res_sep["has_data"] is True
    assert res_sep["record_count"] == 1
    assert "September 2026" in res_sep["available_periods"]

    # Query October -> has_data is False, but available_periods discloses September
    res_oct = check_scope_data_availability(
        records,
        country="EGY",
        team="Coding",
        month="October",
        year=2026,
    )
    assert res_oct["has_data"] is False
    assert res_oct["record_count"] == 0
    assert "September 2026" in res_oct["available_periods"]


def test_9_availability_checks_country_function_and_team_alias_together():
    record = SimpleNamespace(
        month="September",
        year=2026,
        region="EGY",
        employee=SimpleNamespace(team="Inbound"),
    )
    matching = check_scope_data_availability(
        [record], country="Egypt", function="Contact Center", team="inbound agents", month="September", year=2026
    )
    mismatched_function = check_scope_data_availability(
        [record], country="EGY", function="RCM", team="Inbound", month="September", year=2026
    )
    missing_country_evidence = check_scope_data_availability(
        [SimpleNamespace(month="September", year=2026, employee=SimpleNamespace(team="Inbound"))],
        country="EGY", function="Call Center", team="Inbound", month="September", year=2026,
    )
    assert matching["has_data"] is True
    assert mismatched_function["has_data"] is False
    assert missing_country_evidence["has_data"] is False


def test_10_authorized_users_can_select_blocked_team():
    """A user authorized to access a team can select it in the workspace even if AI capability is blocked."""
    catalog = get_ai_catalog()
    scope = {
        "role": "Admin",
        "accessible_teams": ["Inbound", "Finance", "CSR"],
        "accessible_functions": ["Call Center", "Finance", "Customer Service"],
    }
    options = catalog.get_eligible_scope_options(scope)
    # Even though Finance and CSR are blocked for AI capability, they appear in eligible scope options
    team_names = [t.value for t in options["eligible_teams"]]
    assert "Finance" in team_names
    assert "CSR" in team_names


def test_11_blocked_operation_returns_guarded_answer(monkeypatch):
    """A blocked operation returns a guarded answer or disclosure, never invented numbers."""
    session = _build_test_db_session()
    scope = {"role": "Admin", "accessible_teams": ["Finance"], "accessible_functions": ["Finance"]}
    orchestrator = PmsAiOrchestrator(session, scope)

    # Empty records for Finance
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_records", lambda _self, **_kw: [])
    monkeypatch.setattr("services.dashboard_record_service.DashboardRecordService.list_analysis_records", lambda _self, **_kw: [])

    res = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="What is the average score for Finance in September 2026?",
            session_state=SessionFilterContext(team="Finance", month="September", year=2026),
            provider_override="deterministic",
        )
    )
    # Must report no data / blocked / no matched records, not invent a score
    h_lower = res.headline.lower()
    assert "no performance records" in h_lower or "no data" in h_lower or "not available" in h_lower or "blocked" in h_lower
    assert "100%" not in res.headline


def test_12_scope_and_permissions_enforced_independently_of_capability(monkeypatch):
    """A user cannot access teams outside their authorization, regardless of whether the team is verified."""
    session = _build_test_db_session()
    # User only has access to Outbound, but tries to query Inbound (which is partial for operational_summary)
    scope = {"role": "Agent", "accessible_teams": ["Outbound"], "accessible_functions": ["Call Center"]}
    orchestrator = PmsAiOrchestrator(session, scope)

    res = orchestrator.run_chat_turn(
        AiChatRequest(
            prompt="Show me Inbound performance for September 2026",
            session_state=SessionFilterContext(team="Inbound", month="September", year=2026),
            provider_override="deterministic",
        )
    )
    # Access control guardrail must trigger or scope must block access
    assert res.outcome in ("guardrail", "refusal", "restricted_access", "answer")
    if res.outcome == "answer":
        # It must NOT return Inbound records
        assert "access restricted" in res.headline.lower() or "not authorized" in res.headline.lower() or "outbound" in res.headline.lower()
