"""Current grant and parent-selection behavior. No new permission is activated."""
from utils.report_scope import (
    function_for_team,
    function_team_keys,
    functions_for_team,
    selection_team_keys,
    user_can_access_team,
)


def test_legacy_pre_approvals_grant_excludes_offshore_and_other_rcm_sources():
    legacy = {"role": "Function Director", "accessible_functions": ["Pre-Approvals"]}
    rcm = {"role": "Function Director", "accessible_functions": ["RCM"]}

    assert user_can_access_team(legacy, "Pre-Approvals OP Dubai") is True
    assert user_can_access_team(legacy, "Pre-Approvals IP Final SHJAJM") is True
    assert user_can_access_team(legacy, "Pre-Approvals IP Offshore") is False
    assert user_can_access_team(legacy, "Coding") is False
    assert user_can_access_team(rcm, "Pre-Approvals IP Offshore") is True
    assert user_can_access_team(rcm, "Coding") is True
    assert user_can_access_team(rcm, "CSR") is False


def test_pre_approvals_selection_adds_offshore_without_changing_the_grant_keys():
    assert "pre-approvals ip offshore" in selection_team_keys("Pre-Approvals")
    assert "pre-approvals ip offshore" not in function_team_keys("Pre-Approvals")
    assert "coding" in function_team_keys("RCM")
    assert "coding" not in selection_team_keys("Pre-Approvals")
    assert "pre-approvals op dubai" in selection_team_keys("Pre-Approvals OP Final")
    assert "pre-approvals op final shjajm" in selection_team_keys("Pre-Approvals OP Final")
    assert "pre-approvals ip final dubai" in selection_team_keys("Pre-Approvals IP Final")
    assert "pre-approvals ip final shjajm" in selection_team_keys("Pre-Approvals IP Final")


def test_standalone_functions_are_not_pulled_into_call_center_or_rcm():
    assert function_for_team("CSR") == "CSR"
    assert function_for_team("Pharmacy") == "Pharmacy"
    assert function_for_team("Sales") == "Sales"
    assert function_for_team("Marketing") == "Marketing"
    assert function_for_team("Inbound UAE") == "Inbound UAE"
    assert functions_for_team("Inbound") == ["Call Center"]
    assert functions_for_team("Pre-Approvals OP Dubai") == ["RCM", "Pre-Approvals"]
    assert "csr" not in function_team_keys("Call Center")
    assert "inbound uae" not in function_team_keys("Call Center")
    assert "pharmacy" not in function_team_keys("RCM")
