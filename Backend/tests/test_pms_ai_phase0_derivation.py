"""The Phase 0 derivation script matches the committed v1 files.

It does not call the assistant. v0 stays the unsigned freeze.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PHASE0 = ROOT / "evaluation" / "pms-ai" / "phase0"
SCRIPT = PHASE0 / "derive_expected.py"
FROZEN_V0 = PHASE0 / "frozen_v0.json"
HELDOUT_V0 = PHASE0 / "heldout_v0.json"

FORBIDDEN = (
    "services/ai/",
    "evaluate_ai_classifier",
    "contextual-ai-assistant",
    "pms-ai-conversation-v2",
    "phase6_held_out",
    "RELEASE_MANIFEST",
    "ai_english_questions",
    "conversation_v2",
    "evaluate_full_coverage",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _module():
    spec = importlib.util.spec_from_file_location("derive_expected", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def built() -> dict:
    return _module().build()


def _pending_count(doc: dict) -> int:
    return sum(
        1
        for case in doc["cases"]
        for item in case["expected_values"]
        if item["value"] == "PENDING"
    )


def test_v0_freeze_is_unchanged_and_still_unsigned() -> None:
    frozen = _load(FROZEN_V0)
    heldout = _load(HELDOUT_V0)
    assert frozen["status"] == "frozen_questions_expectations_unsigned"
    assert heldout["status"] == "frozen_questions_expectations_unsigned"
    assert _pending_count(frozen) + _pending_count(heldout) == 190


def test_committed_v1_matches_the_script(built: dict) -> None:
    for name in ("frozen_v1", "heldout_v1"):
        assert _load(PHASE0 / f"{name}.json") == built["documents"][name]
    assert _load(PHASE0 / "derivation_report.json") == built["report"]
    assert (PHASE0 / "DERIVATION.md").read_text(encoding="utf-8") == built["markdown"]


def test_questions_and_behaviour_match_v0(built: dict) -> None:
    originals = {"frozen_v1": _load(FROZEN_V0), "heldout_v1": _load(HELDOUT_V0)}
    for name, doc in built["documents"].items():
        original_cases = originals[name]["cases"]
        assert [case["id"] for case in doc["cases"]] == [case["id"] for case in original_cases]
        for case, original in zip(doc["cases"], original_cases):
            for field in ("question", "group_id", "expected_behaviour", "turns", "runnable"):
                assert case[field] == original[field]
        assert doc["schema_version"] == "pms-ai-phase0-eval-v1"
        assert doc["status"] == "expectations_partially_derived_unsigned"
        assert doc["historical_results"] == "unverified"


def test_fills_are_catalog_or_schema_and_still_unsigned(built: dict) -> None:
    report = built["report"]
    assert report["pending_before"] == 190
    assert report["filled_count"] == 18
    assert report["still_pending_count"] == 172
    assert sum(item["count"] for item in report["still_pending_by_reason"].values()) == 172

    filled = {(item["id"], item["field"]): item["value"] for item in report["filled"]}
    assert filled[("fz-021", "country_binding")] == "EGY"
    assert filled[("ho-001", "country_binding")] == "EGY"
    assert filled[("ho-078", "country_binding")] == "UAE"
    assert filled[("fz-023", "team_binding")] == {"team": "Inbound", "region": "EGY"}
    assert filled[("fz-017", "team_binding")] == {"team": "Coding", "region": "UAE"}
    assert filled[("fz-041", "team_binding")] == {"team": "Pre-Approvals IP", "region": "EGY"}
    assert filled[("fz-043", "team_binding")] == {"team": "Pre-Approvals OP Dubai", "region": "UAE"}
    assert filled[("fz-008", "joiner_flag")] == "no_join_date_source"
    assert filled[("ho-028", "joiner_flag")] == "no_join_date_source"

    originals = {"frozen_v1": _load(FROZEN_V0), "heldout_v1": _load(HELDOUT_V0)}
    for name, doc in built["documents"].items():
        original_cases = {case["id"]: case for case in originals[name]["cases"]}
        grouped: dict[str, dict] = {}
        for case in doc["cases"]:
            prior_values = {
                item["field"]: item for item in original_cases[case["id"]]["expected_values"]
            }
            grouped.setdefault(case["group_id"], {})
            for item in case["expected_values"]:
                assert item["reviewer"] == "PENDING"
                prior = prior_values[item["field"]]
                if item["value"] == "PENDING":
                    assert prior["value"] == "PENDING"
                    assert item["source"] == "PENDING"
                    assert item["pending_reason"].strip()
                    continue
                assert item["source"] != "PENDING"
                if prior["value"] != "PENDING":
                    assert item["value"] == prior["value"]
                    assert item["source"] == prior["source"]
                    assert "derivation" not in item
                else:
                    assert item["derivation"]["script"] == "evaluation/pms-ai/phase0/derive_expected.py"
                    assert item["derivation"]["inputs"]
                    blob = json.dumps(item)
                    for marker in FORBIDDEN:
                        assert marker not in blob
                    for source in item["derivation"]["inputs"]:
                        assert len(source["commit"]) == 40
                previous = grouped[case["group_id"]].get(item["field"])
                assert previous in (None, item["value"])
                grouped[case["group_id"]][item["field"]] = item["value"]


def test_outbound_august_total_is_computed_and_not_stored(built: dict) -> None:
    reference = _load(ROOT / "docs/plans/monthly-evaluation/outbound-anonymous-reference.json")
    not_applied = built["report"]["not_applied"]
    assert not_applied["applied_to_expected_values"] is False
    assert not_applied["august_pooled_earned_0_to_1"] == pytest.approx(
        reference["august"]["expected_score"],
        abs=1e-12,
    )
    heldout = built["documents"]["heldout_v1"]
    august = next(case for case in heldout["cases"] if case["id"] == "ho-048")
    score = next(item for item in august["expected_values"] if item["field"] == "august_score")
    assert score["value"] == "PENDING"
    assert "not stored" in score["pending_reason"] or "not the published team score" in score["pending_reason"]

    frozen = built["documents"]["frozen_v1"]
    adham = next(case for case in frozen["cases"] if case["id"] == "fz-025")
    adham_score = next(item for item in adham["expected_values"] if item["field"] == "august_score")
    assert adham_score["value"] == "PENDING"
    assert "roster" in adham_score["pending_reason"]
    assert "pooled" not in adham_score["pending_reason"]
