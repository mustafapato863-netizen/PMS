from types import SimpleNamespace

import pytest

from models.ai_schemas import AiToolCallRecord, SessionFilterContext
from scripts.run_phase6_independent_eval import CONVERSATION_FIXTURE, _score_turn, load_frozen_fixture, render_qa_summary
from services.ai.domain_policies import parse_query_rankings_spec
from services.ai.router import _extract_person_query_from_prompt


def _response(headline, *, region="UAE", month="August", tool="query_rankings"):
    return SimpleNamespace(
        headline=headline,
        narrative_bullets=[],
        detail_bullets=[],
        outcome="answer",
        resolved_session_state=SessionFilterContext(region=region, month=month, year=2026),
        tool_calls=[AiToolCallRecord(tool_name=tool, records_evaluated=2)],
    )


@pytest.mark.parametrize("headline,region,month,tool", [
    ("Sales averaged 176.0%.", "UAE", "August", "query_rankings"),
    ("Sales averaged 76.0 min.", "UAE", "August", "query_rankings"),
    ("Sales averaged 76%.", None, "August", "query_rankings"),
    ("Sales averaged 76%.", "UAE", None, "query_rankings"),
    ("Sales averaged 76%.", "UAE", "July", "query_rankings"),
    ("Sales averaged 76%.", "UAE", "August", "discover_pms_catalog"),
])
def test_incorrect_value_unit_scope_and_operation_fail(headline, region, month, tool):
    turn = {
        "expected_outcome": "answer",
        "required_facts": [{"value": 76, "unit": "%", "subject": "Sales"}],
        "critical_scope": {"region": "UAE", "month": "August", "year": 2026},
        "required_tools": ["query_rankings"],
    }
    assert _score_turn(turn, _response(headline, region=region, month=month, tool=tool))[2] is False
    assert _score_turn(turn, _response("Sales averaged 76.00%."))[2] is True


def test_ranking_requires_both_tied_people_and_verifies_score_position():
    turn = {
        "expected_outcome": "answer",
        "required_ranks": ["Alex Grey", "Sam Lane"],
        "allow_rank_ties": True,
        "required_facts": [{"value": 89, "unit": "%", "subject": "Alex Grey", "ranked": True}],
    }
    assert _score_turn(turn, _response("Alex Grey (89.0%)."))[2] is False
    assert _score_turn(turn, _response("Alex Grey (90%), Sam Lane (89%)."))[2] is False
    assert _score_turn(turn, _response("Sam Lane (89.0%), Alex Grey (89%)."))[2] is True


def test_manifest_detects_changes_and_accepts_windows_newlines(tmp_path):
    import hashlib
    import json

    path = tmp_path / "frozen.json"
    contents = b'{\n"sessions": [{"turns": [{}]}]\n}'
    path.write_bytes(contents.replace(b"\n", b"\r\n"))
    path.with_suffix(".manifest.json").write_text(json.dumps({
        "fixture_sha256": hashlib.sha256(contents).hexdigest(),
        "session_count": 1,
        "turn_count": 1,
    }))
    load_frozen_fixture(path)
    path.write_bytes(contents + b" ")
    with pytest.raises(ValueError, match="manifest mismatch"):
        load_frozen_fixture(path)


def test_conversation_suite_checks_proposal_subject_and_repeated_sentences():
    fixture, manifest = load_frozen_fixture(CONVERSATION_FIXTURE)
    assert manifest["turn_count"] >= 30
    turns = {turn["id"]: turn for session in fixture["sessions"] for turn in session["turns"]}
    response = _response("Recommend a coaching review for Rami Khoury (84.0%).", region="EGY", month="September")
    response.resolved_session_state.team = "Inbound"
    response.action_proposal = SimpleNamespace(employee_id="H-IN-04", month="September", year=2026)
    assert _score_turn(turns["qa07"], response)[0]
    response.action_proposal.employee_id = "H-IN-01"
    assert any("proposal: employee_id" in failure for failure in _score_turn(turns["qa07"], response)[3])

    formatted = {"expected_outcome": "answer", "checks": {"distinct_text": True, "no_tools": True}}
    response.narrative_bullets = [response.headline]
    failures = _score_turn(formatted, response)[1]
    assert any(item.startswith("format:") for item in failures)
    assert any(item.startswith("routing:") for item in failures)


def test_qa_summary_counts_same_failure_once_and_keeps_mode_observations():
    failure = {
        "id": "bad-scope",
        "session": "ranking",
        "prompt": "Which department won?",
        "headline": "The UAE department won.",
        "scope": {"region": "UAE"},
        "critical_failures": ["critical_region_mismatch:UAE!=EGY"],
        "semantic_failures": [],
        "tool_calls": ["query_rankings"],
        "expectations": {},
    }
    run = {
        "denominator": 1, "semantic_passed": 0, "critical_passed": 0,
        "model_synthesis_turns": 0, "first_response_p95_ms": 6, "failures": [failure],
    }
    report = render_qa_summary({"conversation": {"runs": {"baseline": run, "mocked": run}}})
    assert "Scope and conversation context** — 1 distinct failed turns" in report
    assert "**baseline** — The UAE department won" in report
    assert "**mocked** — The UAE department won" in report


@pytest.mark.parametrize(("prompt", "count"), [
    ("Rank the three best staff in this team", 3),
    ("Give me both names at the top of the team scorecard", 2),
    ("Name the employee with the shortest wait time", 1),
])
def test_ranking_preserves_requested_count(prompt, count):
    spec = parse_query_rankings_spec(prompt)
    assert spec is not None
    assert spec.entity == "employee"
    assert spec.limit == count


def test_question_about_an_unknown_ranked_employee_does_not_invent_a_name():
    assert _extract_person_query_from_prompt("Which Inbound employee posted the highest score?") is None
    assert _extract_person_query_from_prompt("Show score for employee Alex Grey") == "Alex Grey"
