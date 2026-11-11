"""Filled Phase 0 bindings are graded from the structured resolution, not the headline."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "evaluation" / "pms-ai" / "phase0" / "run_rules_only_baseline.py"
_saved = os.environ.copy()
spec = importlib.util.spec_from_file_location("run_rules_only_baseline_bindings", SCRIPT)
assert spec is not None and spec.loader is not None
rrb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rrb)
os.environ.clear()
os.environ.update(_saved)

grade = rrb.grade


def _case(field: str, value, *, behaviour: str = "answer", family: str = "current_value", question: str = "What is the score?") -> dict:
    return {
        "id": "binding-test",
        "user_fixture": {"role": "Admin"},
        "expected_behaviour": behaviour,
        "operation_family": family,
        "channel": "dedicated_chat",
        "question": question,
        "expected_values": [{"field": field, "value": value, "reviewer": "PENDING"}],
    }


def _turn(data: dict, *, status: int = 200) -> list[dict]:
    return [{
        "http_status": status,
        "model_attempted": False,
        "response": {"data": data},
    }]


def _resolved(*, team: str | None, region: str | None, outcome: str = "answer", tools: list | None = None) -> dict:
    arguments = {
        "team": team,
        "function": "Call Center",
        "region": region,
        "month": "September",
        "year": 2026,
    }
    return {
        "outcome": outcome,
        "headline": "No performance records matched the selected filters.",
        "resolved_session_state": {"function": "Call Center", "team": team, "region": region},
        "structured_query": {"intent": "current_value", "team": team, "function": "Call Center"},
        "validated_plan_v2": {"scope": {"team": team, "function": "Call Center"}},
        "tool_calls": tools if tools is not None else [
            {"tool_name": "get_team_trend_spotlight", "arguments": arguments}
        ],
    }


def test_team_binding_matches_tool_team_and_region():
    result = grade(
        _case("team_binding", {"team": "Coding", "region": "UAE"}),
        _turn(_resolved(team="Coding", region="UAE")),
    )
    assert result["status"] == "passed"
    assert result["failure_categories"] == []
    assert result["binding_grades"] == [
        {"field": "team_binding", "status": "match", "category": None, "note": result["binding_grades"][0]["note"]}
    ]
    assert result["binding_grades"][0]["status"] == "match"


def test_team_binding_mismatch_is_an_identity_failure():
    result = grade(
        _case("team_binding", {"team": "Inbound", "region": "EGY"}),
        _turn(_resolved(team="Outbound", region="EGY")),
    )
    assert result["status"] == "failed"
    assert "identity" in result["failure_categories"]
    assert result["binding_grades"][0]["status"] == "mismatch"


def test_country_binding_mismatch_is_a_scope_failure():
    result = grade(
        _case("country_binding", "EGY"),
        _turn(_resolved(team="Pharmacy", region="UAE")),
    )
    assert result["status"] == "failed"
    assert "scope" in result["failure_categories"]
    assert "identity" not in result["failure_categories"]


def test_country_binding_missing_from_the_trace_is_ungraded():
    result = grade(
        _case("country_binding", "EGY"),
        _turn(_resolved(team="Marketing", region=None)),
    )
    assert result["status"] == "ungraded"
    assert result["failure_categories"] == []
    assert result["binding_grades"][0]["status"] == "unobservable"
    assert "ungraded" in result["notes"][-1]


def test_team_binding_without_a_region_in_the_trace_is_ungraded():
    result = grade(
        _case("team_binding", {"team": "Inbound", "region": "EGY"}),
        _turn(_resolved(team="Inbound", region=None)),
    )
    assert result["status"] == "ungraded"
    assert result["failure_categories"] == []
    assert result["binding_grades"][0]["status"] == "unobservable"


def test_team_id_match_without_a_display_name():
    data = _resolved(team=None, region="EGY", tools=[{
        "tool_name": "lookup",
        "arguments": {"team_id": "team-inbound", "region": "EGY"},
    }])
    data["resolved_session_state"] = {"team": None, "region": "EGY"}
    data["structured_query"] = {"team": None}
    data["validated_plan_v2"] = {"scope": {"region": "EGY"}}
    result = grade(_case("team_binding", "team-inbound"), _turn(data))
    assert result["binding_grades"][0]["status"] == "match"
    assert result["status"] == "passed"


def test_joiner_flag_matches_when_the_trace_has_no_join_date():
    data = {
        "outcome": "clarification",
        "headline": "PMS tracks monthly evaluation scores rather than employee hire dates.",
        "resolved_session_state": {"team": "Inbound", "region": None},
        "structured_query": {"intent": "clarify", "team": "Inbound"},
        "tool_calls": [],
    }
    result = grade(
        _case("joiner_flag", "no_join_date_source", behaviour="clarify", family="employment_status", question="Is Mariam a new joiner in Inbound?"),
        _turn(data),
    )
    assert result["status"] == "passed"
    assert result["binding_grades"][0]["status"] == "match"


def test_joiner_flag_mismatch_when_a_tool_resolves_a_join_date():
    data = {
        "outcome": "answer",
        "headline": "Mariam joined in January.",
        "resolved_session_state": {"team": "Inbound"},
        "structured_query": {"intent": "clarify", "team": "Inbound"},
        "tool_calls": [{"tool_name": "lookup_employee", "arguments": {"team": "Inbound", "join_date": "2026-01-04"}}],
    }
    result = grade(
        _case("joiner_flag", "no_join_date_source", behaviour="answer", family="employment_status", question="Is Mariam a new joiner in Inbound?"),
        _turn(data),
    )
    assert result["status"] == "failed"
    assert "identity" in result["failure_categories"]
    assert result["binding_grades"][0]["status"] == "mismatch"


def test_joiner_flag_is_ungraded_when_no_structured_trace_exists():
    result = grade(
        _case("joiner_flag", "no_join_date_source", behaviour="clarify", family="employment_status", question="Is Mariam a new joiner?"),
        _turn({"outcome": "clarification", "headline": "Which Mariam?"}),
    )
    assert result["status"] == "ungraded"
    assert result["binding_grades"][0]["status"] == "unobservable"
    assert result["failure_categories"] == []


def test_pending_answer_stays_ungraded_when_no_binding_is_filled():
    case = _case("score", "PENDING")
    result = grade(case, _turn(_resolved(team="Inbound", region="EGY")))
    assert result["status"] == "ungraded"
    assert result["binding_grades"] == []


def test_headline_country_does_not_count_as_resolution():
    data = _resolved(team="Marketing", region=None)
    data["headline"] = "Marketing in EGY scored nothing."
    result = grade(_case("country_binding", "EGY"), _turn(data))
    assert result["status"] == "ungraded"
    assert result["binding_grades"][0]["status"] == "unobservable"


def test_team_name_matches_when_trace_also_carries_a_team_id():
    # A short slug id next to the display name is the same team, not a
    # second team. The old shape-based split counted it as another name
    # and failed a matching binding.
    data = _resolved(team="Coding", region="UAE", tools=[{
        "tool_name": "get_team_trend_spotlight",
        "arguments": {
            "team": "Coding", "team_id": "team-coding", "function": "Call Center",
            "region": "UAE", "month": "September", "year": 2026,
        },
    }])
    result = grade(
        _case("team_binding", {"team": "Coding", "region": "UAE"}),
        _turn(data),
    )
    assert result["status"] == "passed"
    assert result["binding_grades"][0]["status"] == "match"


def test_team_id_matches_when_trace_also_carries_a_display_name():
    # A UUID id next to its display name is the same team, not a conflict.
    team_id = "12345678-1234-1234-1234-123456789012"
    data = _resolved(team="Inbound", region="EGY", tools=[{
        "tool_name": "lookup",
        "arguments": {"team": "Inbound", "team_id": team_id, "region": "EGY"},
    }])
    result = grade(_case("team_binding", team_id), _turn(data))
    assert result["status"] == "passed"
    assert result["binding_grades"][0]["status"] == "match"


def test_team_name_against_id_only_trace_is_ungraded_not_a_mismatch():
    # An opaque id alone cannot be compared with a display name.
    team_id = "12345678-1234-1234-1234-123456789012"
    data = _resolved(team=None, region="EGY", tools=[{
        "tool_name": "lookup",
        "arguments": {"team_id": team_id, "region": "EGY"},
    }])
    data["resolved_session_state"] = {"team": None, "region": "EGY"}
    data["structured_query"] = {"team": None}
    data["validated_plan_v2"] = {"scope": {"region": "EGY"}}
    result = grade(
        _case("team_binding", {"team": "Coding", "region": "EGY"}),
        _turn(data),
    )
    assert result["status"] == "ungraded"
    assert result["failure_categories"] == []
    assert result["binding_grades"][0]["status"] == "unobservable"


def test_team_binding_with_team_and_region_mismatch_reports_both_categories():
    result = grade(
        _case("team_binding", {"team": "Outbound", "region": "UAE"}),
        _turn(_resolved(team="Inbound", region="EGY")),
    )
    assert result["status"] == "failed"
    assert result["failure_categories"] == ["identity", "scope"]
    assert result["binding_grades"][0]["status"] == "mismatch"


def test_errored_grade_still_reports_binding_grades():
    result = grade(
        _case("team_binding", {"team": "Coding", "region": "UAE"}),
        [{"http_status": 500, "model_attempted": False, "response": {}}],
    )
    assert result["status"] == "errored"
    assert result["binding_grades"] == []


def test_load_cases_selects_question_set_version(monkeypatch):
    monkeypatch.delenv("PMS_PHASE0_SET_VERSION", raising=False)
    assert rrb.question_set_version() == "v0"
    v0 = rrb.load_cases()
    assert len(v0) == 136
    assert {case["set_id"] for case in v0} == {"frozen_v0", "heldout_v0"}
    assert rrb.load_cases("v0")[0]["set_id"].endswith("_v0")

    v1 = rrb.load_cases("v1")
    assert len(v1) == 136
    assert {case["set_id"] for case in v1} == {"frozen_v1", "heldout_v1"}
    filled = [
        case["id"] for case in v1
        for item in case["expected_values"]
        if item["field"] in rrb.BINDING_FIELDS and item["value"] != "PENDING"
    ]
    assert len(filled) == 18

    monkeypatch.setenv("PMS_PHASE0_SET_VERSION", "v1")
    assert rrb.question_set_version() == "v1"
    assert {case["set_id"] for case in rrb.load_cases()} == {"frozen_v1", "heldout_v1"}

    monkeypatch.setenv("PMS_PHASE0_SET_VERSION", "v2")
    with pytest.raises(ValueError, match="PMS_PHASE0_SET_VERSION"):
        rrb.question_set_version()
    with pytest.raises(ValueError, match="Unknown question-set version"):
        rrb.load_cases("v2")
