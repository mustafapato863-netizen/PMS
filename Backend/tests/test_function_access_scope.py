from types import SimpleNamespace

from utils.report_scope import filter_records_by_scope, user_can_access_team


def record(team: str):
    return SimpleNamespace(team=team, employee_id="E-1")


def test_function_viewer_scope_filters_records_and_team_drilldowns():
    scope = {
        "role": "Function Viewer",
        "accessible_functions": ["Call Center"],
        "accessible_teams": [],
        "legacy_unscoped": False,
    }

    visible = filter_records_by_scope(
        [record("Inbound"), record("Outbound"), record("Coding"), record("Marketing")],
        scope,
    )

    assert [row.team for row in visible] == ["Inbound", "Outbound"]
    assert user_can_access_team(scope, "Inbound") is True
    assert user_can_access_team(scope, "Coding") is False


def test_function_viewer_without_grants_fails_closed_even_for_legacy_scope():
    scope = {
        "role": "Function Viewer",
        "accessible_functions": [],
        "legacy_unscoped": True,
    }

    assert filter_records_by_scope([record("Coding"), record("Inbound")], scope) == []
    assert user_can_access_team(scope, "Coding") is False


def test_function_membership_preserves_configured_overlap():
    scope = {
        "role": "Function Viewer",
        "accessible_functions": ["RCM"],
        "legacy_unscoped": False,
    }

    assert user_can_access_team(scope, "Pre-Approvals OP Final") is True
    assert [
        row.team for row in filter_records_by_scope(
            [record("Pre-Approvals OP Final"), record("Inbound")],
            scope,
        )
    ] == ["Pre-Approvals OP Final"]


def test_manager_branch_assignment_stays_limited_to_selected_team():
    scope = {
        "role": "Manager",
        "accessible_teams": ["Coding"],
        "has_unrestricted_team_access": False,
        "legacy_unscoped": False,
    }

    assert [row.team for row in filter_records_by_scope(
        [record("Coding"), record("Submission")],
        scope,
    )] == ["Coding"]


def test_function_viewer_sql_scope_uses_only_granted_function_teams():
    from repositories.performance_repository import PerformanceRepository

    class QueryCapture:
        def __init__(self):
            self.predicates = []

        def filter(self, predicate):
            self.predicates.append(predicate)
            return self

    query = QueryCapture()
    scope = {
        "role": "Function Viewer",
        "accessible_functions": ["RCM"],
        # Even a legacy marker must not bypass this role's explicit scope.
        "legacy_unscoped": True,
    }

    assert PerformanceRepository._apply_scope(query, scope) is query
    assert len(query.predicates) == 1
    clause = str(query.predicates[0].compile(compile_kwargs={"literal_binds": True})).casefold()
    assert "coding" in clause
    assert "submission" in clause
    assert "inbound" not in clause


def test_function_viewer_can_use_globally_enabled_scoped_read_api(monkeypatch):
    from api.routers.performance import _require_scoped_read_api
    from config import settings

    monkeypatch.setattr(settings, "PMS_SCOPED_PERFORMANCE_API_ENABLED", True)
    monkeypatch.setattr(settings, "PMS_SCOPED_PERFORMANCE_ALLOWED_ROLES", ("Admin",))

    _require_scoped_read_api({"role": "Function Viewer", "accessible_functions": ["RCM"]})


def test_sql_scope_with_no_function_grants_matches_no_rows():
    from repositories.performance_repository import PerformanceRepository

    class QueryCapture:
        def __init__(self):
            self.predicates = []

        def filter(self, predicate):
            self.predicates.append(predicate)
            return self

    query = QueryCapture()
    PerformanceRepository._apply_scope(
        query,
        {"role": "Function Viewer", "accessible_functions": [], "legacy_unscoped": True},
    )

    assert len(query.predicates) == 1
    assert str(query.predicates[0]).casefold() == "false"
