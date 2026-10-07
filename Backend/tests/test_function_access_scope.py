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


def test_function_director_uses_the_existing_function_assignment_scope():
    scope = {
        "role": "Function Director",
        "accessible_functions": ["Marketing"],
        "legacy_unscoped": False,
    }
    visible = filter_records_by_scope(
        [record("Marketing"), record("Coding")],
        scope,
    )
    assert [row.team for row in visible] == ["Marketing"]
    assert user_can_access_team(scope, "Marketing") is True
    assert user_can_access_team(scope, "Coding") is False


def test_branch_director_requires_one_explicit_branch_and_ignores_geo_totals():
    dubai = SimpleNamespace(
        team="Inbound",
        employee_id="E-1",
        raw_data={"Branch": "Dubai"},
        geo=SimpleNamespace(bookings=SimpleNamespace(dubai=50)),
    )
    geo_only = SimpleNamespace(
        team="Inbound",
        employee_id="E-2",
        raw_data={"Agent": "No branch field"},
        geo=SimpleNamespace(bookings=SimpleNamespace(dubai=50)),
    )
    ambiguous = SimpleNamespace(
        team="Pre-Approvals IP Final SHJ & AJM",
        employee_id="E-3",
        raw_data={"Team": "Pre-Approvals IP Final SHJ & AJM"},
    )
    scope = {
        "role": "Branch Director",
        "accessible_branches": ["dubai"],
        "legacy_unscoped": False,
    }

    assert filter_records_by_scope([dubai, geo_only, ambiguous], scope) == [dubai]


def test_regional_manager_scope_intersects_region_and_assigned_teams():
    scope = {
        "role": "Regional Manager",
        "accessible_regions": ["UAE"],
        "accessible_teams": ["Inbound"],
        "legacy_unscoped": False,
    }
    records = [
        SimpleNamespace(team="Inbound", region="UAE"),
        SimpleNamespace(team="Inbound", region="EGY"),
        SimpleNamespace(team="Coding", region="UAE"),
    ]

    assert filter_records_by_scope(records, scope) == [records[0]]
    assert user_can_access_team(scope, "Inbound") is True
    assert user_can_access_team(scope, "Coding") is False


def test_regional_manager_uses_employee_or_team_region_when_record_region_is_missing():
    scope = {
        "role": "Regional Manager",
        "accessible_regions": ["UAE"],
        "accessible_teams": ["Inbound"],
        "legacy_unscoped": False,
    }
    from_employee = SimpleNamespace(
        team="Inbound", region=None, employee=SimpleNamespace(region="UAE")
    )
    from_team = SimpleNamespace(
        region="", employee=None
    )
    from_team.team = SimpleNamespace(name="Inbound", region="UAE")
    outside_region = SimpleNamespace(
        team="Inbound", region=None, employee=SimpleNamespace(region="EGY")
    )

    assert filter_records_by_scope([from_employee, from_team, outside_region], scope) == [
        from_employee,
        from_team,
    ]


def test_branch_director_accepts_casefolded_canonical_branch_key():
    row = SimpleNamespace(team="Inbound", employee_id="E-1", branch_key="Dubai")
    scope = {"role": "Branch Director", "accessible_branches": ["dubai"]}

    assert filter_records_by_scope([row], scope) == [row]


def test_employee_scope_is_self_only_and_performance_team_is_global():
    records = [
        SimpleNamespace(team="Inbound", employee_id="E-1"),
        SimpleNamespace(team="Inbound", employee_id="E-2"),
    ]

    employee_scope = {
        "role": "Employee",
        "employee_id": "E-1",
        "user_id": "user-1",
        "legacy_unscoped": False,
    }
    performance_scope = {"role": "Performance Team", "legacy_unscoped": False}

    assert filter_records_by_scope(records, employee_scope) == [records[0]]
    assert filter_records_by_scope(records, performance_scope) == records


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
