"""Insights workspace `sections`: a build computes only the requested fields, and a field's output never depends on
which other fields were requested. Synthetic records only.
"""

import json

import pytest
from fastapi import HTTPException

from models.insight_schemas import InsightFilterOptions, InsightsWorkspace, InsightSummary
from models.schemas import EvaluationData, PerformanceRecord
from services.insights_service import WORKSPACE_SECTIONS, InsightsService, InsightValidationError
from services.planning_service import PlanningService

# The fields the Insights page renders. The frontend requests the same list (features/insights, INSIGHTS_PAGE_SECTIONS).
PAGE_SECTIONS = (
    "summary",
    "options",
    "comparison",
    "executive_story",
    "priority_insights",
    "people_contribution_analysis",
    "kpi_trend",
    "kpi_diagnosis",
    "tracking_indicators",
    "team_summaries",
    "role_summaries",
    "performance_drivers",
    "risks",
    "opportunities",
)


class StubRepository:
    def __init__(self, records):
        self.records = records

    def get_all(self):
        return self.records


def _kpi(key, label, actual, target, weight, direction="higher_better", unit="%"):
    if direction == "lower_better":
        achievement = 1.0 if actual <= 0 else min(target / actual, 1.0)
    else:
        achievement = min(actual / target, 1.0) if target else 0.0
    return {
        "kpi_key": key,
        "label": label,
        "direction": direction,
        "unit": unit,
        "actual_value": actual,
        "target_value": target,
        "weight_applied": weight,
        "contribution": achievement * weight,
    }


def _record(employee_id, team, position, kpis, month, score):
    return PerformanceRecord(
        id=f"{employee_id}_2026_{month}",
        employee_id=employee_id,
        employee_name=f"Synthetic {employee_id}",
        team=team,
        month=month,
        year=2026,
        region="EGY",
        position=position,
        performance_level="Employee",
        status="Below",
        evaluation=EvaluationData(score=score, grade="C"),
        kpi_values=kpis,
    )


def _fixture_records():
    records = []
    for month_index, month in enumerate(("May", "June")):
        for employee_index in range(3):
            cpl = 50.0 + 10 * employee_index + 5 * month_index
            quality = 0.90 + 0.02 * employee_index - 0.01 * month_index
            records.append(_record(
                f"A{employee_index}", "Synthetic Alpha", "Agent",
                [
                    _kpi("a_cpl", "CPL", cpl, 60.0, 0.4, direction="lower_better", unit="AED"),
                    _kpi("a_quality", "Quality", quality, 0.95, 0.6),
                ],
                month, 55.0 + 5 * employee_index - 2 * month_index,
            ))
        for employee_index in range(2):
            sla = 0.80 + 0.03 * employee_index - 0.02 * month_index
            response = 4.0 + 1.5 * employee_index + month_index
            records.append(_record(
                f"B{employee_index}", "Synthetic Beta", "Coach",
                [
                    _kpi("b_sla", "SLA", sla, 0.9, 0.5),
                    _kpi("b_resp", "Response", response, 5.0, 0.5, direction="lower_better", unit="min"),
                ],
                month, 62.0 + 4 * employee_index,
            ))
    return records


def _scope():
    return {
        "role": "Admin",
        "has_unrestricted_team_access": True,
        "legacy_unscoped": False,
        "accessible_teams": [],
        "accessible_team_levels": [],
    }


def _service(records=None):
    records = _fixture_records() if records is None else records
    repository = StubRepository(records)
    service = InsightsService(repository, PlanningService(repository))
    service._authorized_records = lambda _scope: (records, 0)
    return service


def _dump(value):
    if isinstance(value, list):
        dumped = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
    elif hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
    else:
        dumped = value
    return json.dumps(dumped, sort_keys=True)


def _fields(workspace, names):
    return {name: _dump(getattr(workspace, name)) for name in names}


def _spy(monkeypatch, name):
    """Record each call of an InsightsService method without changing what it returns."""
    calls = []
    original = InsightsService.__dict__[name]
    is_static = isinstance(original, staticmethod)
    function = original.__func__ if is_static else original

    def wrapper(*args, **kwargs):
        calls.append(name)
        return function(*args, **kwargs)

    monkeypatch.setattr(InsightsService, name, staticmethod(wrapper) if is_static else wrapper)
    return calls


JUNE = {"month": "June", "year": 2026}


def test_absent_sections_compute_every_field_as_before():
    service = _service()

    absent = service.generate_workspace(_scope(), **JUNE)
    explicit_all = service.generate_workspace(_scope(), sections=list(WORKSPACE_SECTIONS), **JUNE)
    none = service.generate_workspace(_scope(), sections=None, **JUNE)

    assert absent.model_dump_json() == explicit_all.model_dump_json() == none.model_dump_json()
    # The fixture must make the big fields non-empty, or the equality above proves nothing.
    assert absent.priority_insights and absent.executive_story is not None
    assert absent.kpi_diagnosis and absent.people_contribution_analysis is not None
    assert absent.kpi_trend is not None and absent.team_analyses and absent.team_summaries


def test_the_page_sections_are_byte_identical_with_and_without_the_parameter():
    service = _service()

    full = service.generate_workspace(_scope(), **JUNE)
    page = service.generate_workspace(_scope(), sections=PAGE_SECTIONS, **JUNE)

    assert _fields(full, PAGE_SECTIONS) == _fields(page, PAGE_SECTIONS)


@pytest.mark.parametrize("requested", [
    PAGE_SECTIONS,
    ("priority_insights",),
    ("priority_insights", "performance_drivers", "risks", "opportunities", "data_issues"),
    ("kpi_trend", "kpi_diagnosis"),
    ("people_contribution_analysis", "kpi_trend"),
    ("team_summaries", "geography_summaries", "role_summaries"),
    ("team_analyses", "summary"),
    ("executive_story", "overall_trend", "kpi_overview"),
    ("comparison", "deferred_capabilities"),
])
def test_each_requested_field_is_identical_whatever_else_is_requested(requested):
    service = _service()
    alone = service.generate_workspace(_scope(), sections=requested, **JUNE)
    with_others = service.generate_workspace(
        _scope(), sections=sorted(set(requested) | {"comparison", "overall_trend", "summary", "team_summaries"}), **JUNE,
    )
    everything = service.generate_workspace(_scope(), **JUNE)

    assert _fields(alone, requested) == _fields(with_others, requested) == _fields(everything, requested)


@pytest.mark.parametrize("filters", [
    {"team": "Synthetic Alpha"},
    {"team": "Synthetic Beta", "kpi": "b_resp"},
    {"kpi": "a_cpl"},
    {"severity": "critical"},
])
def test_the_page_fields_are_unchanged_under_filters(filters):
    service = _service()
    full = service.generate_workspace(_scope(), **JUNE, **filters)
    page = service.generate_workspace(_scope(), sections=PAGE_SECTIONS, **JUNE, **filters)

    assert _fields(full, PAGE_SECTIONS) == _fields(page, PAGE_SECTIONS)


def test_unrequested_fields_come_back_as_empty_defaults():
    workspace = _service().generate_workspace(_scope(), sections=["comparison"], **JUNE)

    assert workspace.summary == InsightSummary()
    assert workspace.priority_insights == []
    assert workspace.team_analyses == []
    assert workspace.kpi_diagnosis == []
    assert workspace.executive_story is None
    assert workspace.people_contribution_analysis is None
    assert workspace.kpi_trend is None
    assert workspace.options == InsightFilterOptions()
    assert workspace.comparison.current is not None
    assert workspace.deferred_capabilities == []


def test_an_unrequested_field_is_never_computed(monkeypatch):
    spies = {name: _spy(monkeypatch, name) for name in (
        "_kpi_overview", "_overall_trend", "_role_summaries", "_kpi_diagnosis", "_tracking_indicators",
        "_executive_story", "_scope_summaries", "_six_month_values", "_person_pairs", "_options",
        "_kpi_insights", "_score_insights", "_data_quality_items", "_employee_risks",
        "_operational_kpi_insights", "_people_contribution_analysis", "_kpi_trend",
    )}

    _service().generate_workspace(_scope(), sections=["kpi_overview"], **JUNE)

    assert spies["_kpi_overview"] == ["_kpi_overview"]
    for name in ("_overall_trend", "_role_summaries", "_kpi_diagnosis", "_tracking_indicators", "_executive_story",
                 "_scope_summaries", "_six_month_values", "_person_pairs", "_options", "_kpi_insights",
                 "_score_insights", "_data_quality_items", "_employee_risks", "_operational_kpi_insights",
                 "_people_contribution_analysis", "_kpi_trend"):
        assert spies[name] == [], name


def test_shared_work_is_computed_once_for_the_trend_and_the_diagnosis(monkeypatch):
    six_month = _spy(monkeypatch, "_six_month_values")
    pairs = _spy(monkeypatch, "_person_pairs")
    kpi_insights = _spy(monkeypatch, "_kpi_insights")

    _service().generate_workspace(_scope(), sections=["kpi_trend", "kpi_diagnosis", "people_contribution_analysis"], **JUNE)

    assert len(six_month) == 1
    assert len(pairs) == 1
    assert len(kpi_insights) == 1


def test_the_sections_list_can_be_given_as_a_comma_separated_string():
    service = _service()

    as_list = service.generate_workspace(_scope(), sections=["options", "comparison"], **JUNE)
    as_string = service.generate_workspace(_scope(), sections="options, comparison", **JUNE)

    assert as_list.model_dump_json() == as_string.model_dump_json()


@pytest.mark.parametrize("sections", ["summary,not_a_field", "", " , ", ["kpi_diagnosis", "bogus"]])
def test_unknown_or_empty_sections_are_rejected(sections):
    with pytest.raises(InsightValidationError):
        _service().generate_workspace(_scope(), sections=sections, **JUNE)


def test_the_priority_view_keeps_its_own_output_and_ignores_sections():
    service = _service()

    plain = service.generate_workspace(_scope(), priority_only=True, **JUNE)
    with_sections = service.generate_workspace(_scope(), priority_only=True, sections=["options"], **JUNE)

    assert plain.model_dump_json() == with_sections.model_dump_json()


def test_the_endpoint_forwards_sections_and_turns_a_bad_list_into_422(monkeypatch):
    from api.routers import insights as router

    seen = []

    class RecordingService:
        def __init__(self, *args, **kwargs):
            pass

        def generate_workspace(self, scope, **kwargs):
            seen.append(kwargs.get("sections"))
            if kwargs.get("sections") == "bogus":
                raise InsightValidationError("Unknown workspace sections: bogus")
            return _service().generate_workspace(scope, sections=kwargs.get("sections"), **JUNE)

    monkeypatch.setattr(router, "InsightsService", RecordingService)
    monkeypatch.setattr(router, "require_authenticated_scope", lambda db, request: _scope())

    response = router.get_insights_workspace(
        request=None, db=None, month="June", year=2026, sections="options,comparison", _role="Admin",
    )
    assert response.data.comparison.current is not None
    assert seen == ["options,comparison"]

    with pytest.raises(HTTPException) as rejected:
        router.get_insights_workspace(request=None, db=None, sections="bogus", _role="Admin")
    assert rejected.value.status_code == 422


def test_the_diagnosis_people_sums_equal_the_full_people_analysis_for_every_kpi():
    records = _fixture_records()
    current = [record for record in records if record.month == "June"]
    previous = [record for record in records if record.month == "May"]
    current_pairs, _ = InsightsService._person_pairs(current, previous)

    for key in ("a_cpl", "a_quality", "b_sla", "b_resp"):
        full = InsightsService._people_contribution_analysis(key, current, previous)
        impacts, below_target = InsightsService._people_impacts(current_pairs.get(key, []))
        assert impacts == [row.weighted_impact for row in full.rows if row.weighted_impact is not None], key
        assert below_target == full.negative_contributors, key


def test_the_section_names_are_exactly_the_workspace_fields():
    assert set(PAGE_SECTIONS) <= set(WORKSPACE_SECTIONS)
    assert set(WORKSPACE_SECTIONS) == set(InsightsWorkspace.model_fields)
