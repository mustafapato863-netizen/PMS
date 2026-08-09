from repositories.performance_repository import _team_filter_values
from utils.report_scope import _team_keys


def test_ip_final_repository_alias_reads_both_source_teams():
    assert _team_filter_values("Pre-Approvals IP Final") == (
        "pre-approvals ip final dubai",
        "pre-approvals ip final shjajm",
    )


def test_ip_final_scope_alias_keeps_source_and_canonical_names_in_one_scope():
    keys = _team_keys("Pre-Approvals IP Final")
    assert {
        "pre-approvals ip final",
        "pre-approvals ip final dubai",
        "pre-approvals ip final shjajm",
    } <= keys


def test_pre_approvals_parent_repository_alias_reads_all_uae_sources():
    assert _team_filter_values("Pre-Approvals") == (
        "pre-approvals op dubai",
        "pre-approvals op final shjajm",
        "pre-approvals ip final dubai",
        "pre-approvals ip final shjajm",
        "pre-approvals ip elective dubai",
    )


def test_pre_approvals_parent_scope_includes_elective_source():
    assert "pre-approvals ip elective dubai" in _team_keys("Pre-Approvals")


def test_workflow_scope_aliases_do_not_cross_grant_other_workflows():
    assert "pre-approvals op dubai" in _team_keys("Pre-Approvals OP Final")
    assert "pre-approvals ip final dubai" not in _team_keys("Pre-Approvals OP Final")
    assert "pre-approvals ip elective dubai" not in _team_keys("Pre-Approvals IP Final")


def test_team_level_scope_expands_pre_approvals_parent_aliases():
    records = [
        {"team": "Pre-Approvals IP Final Dubai", "performance_level": "Employee"},
        {"team": "Pre-Approvals OP Final SHJAJM", "performance_level": "Employee"},
        {"team": "Pre-Approvals IP Elective Dubai", "performance_level": "Employee"},
    ]
    from utils.report_scope import filter_records_by_team_levels

    scope = {
        "role": "Manager",
        "accessible_team_levels": [("Pre-Approvals", "Employee")],
    }
    assert filter_records_by_team_levels(records, scope) == records


def test_call_center_parent_repository_alias_reads_only_egypt_channels():
    assert _team_filter_values("Call Center") == ("inbound", "outbound")


def test_call_center_parent_scope_does_not_include_inbound_uae():
    assert {"call center", "inbound", "outbound"} <= _team_keys("Call Center")
    assert "inbound uae" not in _team_keys("Call Center")


def test_rcm_parent_scope_includes_all_revenue_cycle_domains():
    keys = _team_keys("RCM")
    assert {
        "rcm",
        "coding",
        "submission",
        "re-submission",
        "pre-approvals ip offshore",
        "pre-approvals op dubai",
        "pre-approvals ip final shjajm",
    } <= keys
