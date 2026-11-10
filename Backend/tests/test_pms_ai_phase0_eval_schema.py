"""Schema gate for the unsigned Phase 0 PMS AI evaluation set.

Checks the frozen and held-out files only. It does not call a model, open a
database, or score an answer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "evaluation" / "pms-ai" / "phase0"
FROZEN_PATH = ROOT / "frozen_v0.json"
HELDOUT_PATH = ROOT / "heldout_v0.json"

SCHEMA_VERSION = "pms-ai-phase0-eval-v0"
SPLIT_RULE_ID = "phase0-paraphrase-group-disjoint-v0"
BEHAVIOURS = {"answer", "clarify", "refuse", "no-data"}
FAMILIES = {
    "greeting",
    "ranking",
    "person_period",
    "employment_status",
    "branch_comparison",
    "trend",
    "corrective_action",
    "cross_department",
    "compound",
    "follow_up",
    "ambiguous_identity",
    "tie",
    "data_state",
    "shared_ownership",
    "same_name_team",
    "access_denial",
    "prompt_injection",
    "navigation",
    "current_value",
    "unsupported",
}
FAILURES = {
    "intent",
    "identity",
    "scope",
    "source",
    "calculation",
    "composition",
    "ui",
    "latency",
}
COUNTRIES = {"EGY", "UAE", "All", "unspecified", "mixed"}
CHANNELS = {
    "dedicated_chat",
    "contextual_panel",
    "direct_api",
    "uploaded_label",
    "ui_surface",
}
INTERACTIONS = {
    "single_turn",
    "multi_turn_inherit",
    "multi_turn_override",
    "multi_turn_confirm",
}
GROUP_FIELDS = (
    "operation_family",
    "expected_behaviour",
    "country",
    "function",
    "team",
    "position",
    "level",
    "period",
    "channel",
    "interaction",
    "page_context",
)
CASE_KEYS = {
    "id",
    "group_id",
    "question",
    "turns",
    "user_fixture",
    "country",
    "function",
    "team",
    "position",
    "level",
    "period",
    "page_context",
    "channel",
    "interaction",
    "operation_family",
    "required_answer_parts",
    "expected_behaviour",
    "expected_values",
    "allowed_provider",
    "allowed_fallback",
    "failure_categories",
    "runnable",
    "provenance",
}
ROADMAP_QUESTIONS = {
    "Hi",
    "Lowest person in support team and position?",
    "Was Adham's best month September?",
    "Is Mariam a new joiner in Inbound?",
    "Which branch most bookings: Dubai, Ajman, Sharjah?",
    "How did Coding perform over six months?",
    "Why did it fall, suggest an action?",
}


def _load(path: Path) -> dict:
    assert path.is_file(), path
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _paraphrase_key(case: dict) -> tuple:
    turns = tuple(
        (turn["speaker"], _norm(turn["text"])) for turn in case["turns"]
    )
    return (
        case["user_fixture"]["fixture_id"],
        case["channel"],
        case["page_context"],
        turns,
    )


@pytest.fixture(scope="module")
def documents() -> dict[str, dict]:
    return {"frozen_v0": _load(FROZEN_PATH), "heldout_v0": _load(HELDOUT_PATH)}


def test_set_metadata(documents: dict[str, dict]) -> None:
    for set_id, doc in documents.items():
        assert doc["schema_version"] == SCHEMA_VERSION
        assert doc["set_id"] == set_id
        assert doc["split_rule_id"] == SPLIT_RULE_ID
        assert doc["status"] == "frozen_questions_expectations_unsigned"
        assert doc["historical_results"] == "unverified"
        assert doc["cases"], set_id


def test_required_fields_and_enums(documents: dict[str, dict]) -> None:
    seen_ids: set[str] = set()
    for set_id, doc in documents.items():
        prefix = "fz-" if set_id == "frozen_v0" else "ho-"
        for case in doc["cases"]:
            missing = CASE_KEYS - case.keys()
            assert not missing, (case.get("id"), missing)
            assert case["id"].startswith(prefix)
            assert case["id"] not in seen_ids
            seen_ids.add(case["id"])
            assert case["group_id"]
            assert case["operation_family"] in FAMILIES
            assert case["expected_behaviour"] in BEHAVIOURS
            assert case["country"] in COUNTRIES
            assert case["channel"] in CHANNELS
            assert case["interaction"] in INTERACTIONS
            assert case["required_answer_parts"]
            assert all(isinstance(part, str) and part for part in case["required_answer_parts"])
            assert set(case["failure_categories"]) <= FAILURES
            assert case["failure_categories"]
            assert case["allowed_provider"]
            assert set(case["allowed_provider"]) <= {"qwen", "rules"}
            assert case["allowed_fallback"]
            assert all(isinstance(item, str) and item for item in case["allowed_fallback"])
            fixture = case["user_fixture"]
            assert fixture["fixture_id"] and fixture["role"] and fixture["display_name"]
            assert case["turns"]
            user_turns = [turn for turn in case["turns"] if turn["speaker"] == "user"]
            assert user_turns, case["id"]
            assert _norm(case["question"]) == _norm(user_turns[-1]["text"])
            provenance = case["provenance"]
            assert provenance["expectation_origin"]
            if provenance["reused_question_from"]:
                assert provenance["historical_result_status"] == "unverified"


def test_expected_values_are_unsigned_and_contain_no_invented_numbers(
    documents: dict[str, dict],
) -> None:
    for doc in documents.values():
        for case in doc["cases"]:
            assert case["expected_values"], case["id"]
            for item in case["expected_values"]:
                assert item["reviewer"] == "PENDING", case["id"]
                assert item["pending_needs"].strip(), case["id"]
                if item["value"] == "PENDING":
                    assert item["source"] == "PENDING", case["id"]
                else:
                    assert item["source"] != "PENDING", case["id"]
                    assert not any(ch.isdigit() for ch in str(item["value"])), (
                        case["id"],
                        item["value"],
                    )


def test_groups_are_internally_consistent_and_disjoint(
    documents: dict[str, dict],
) -> None:
    frozen_groups = {case["group_id"] for case in documents["frozen_v0"]["cases"]}
    held_groups = {case["group_id"] for case in documents["heldout_v0"]["cases"]}
    assert frozen_groups.isdisjoint(held_groups)

    keys_by_file: dict[str, dict[tuple, str]] = {}
    for set_id, doc in documents.items():
        grouped: dict[str, list[dict]] = {}
        keys_by_file[set_id] = {}
        for case in doc["cases"]:
            grouped.setdefault(case["group_id"], []).append(case)
            key = _paraphrase_key(case)
            previous = keys_by_file[set_id].get(key)
            assert previous in (None, case["group_id"]), (key, previous, case["group_id"])
            keys_by_file[set_id][key] = case["group_id"]
        if set_id == "heldout_v0":
            short = [gid for gid, items in grouped.items() if len(items) < 2]
            assert not short, short
        for items in grouped.values():
            base = items[0]
            for case in items[1:]:
                for field in GROUP_FIELDS:
                    assert case[field] == base[field], (case["id"], field)
                assert case["user_fixture"]["fixture_id"] == base["user_fixture"]["fixture_id"]

    assert set(keys_by_file["frozen_v0"]).isdisjoint(keys_by_file["heldout_v0"])


def test_frozen_contains_roadmap_required_answers(documents: dict[str, dict]) -> None:
    questions = {case["question"] for case in documents["frozen_v0"]["cases"]}
    assert ROADMAP_QUESTIONS <= questions


def test_both_sets_exercise_every_failure_category(documents: dict[str, dict]) -> None:
    for doc in documents.values():
        seen = {category for case in doc["cases"] for category in case["failure_categories"]}
        assert seen == FAILURES
