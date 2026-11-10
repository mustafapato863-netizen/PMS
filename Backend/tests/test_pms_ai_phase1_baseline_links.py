"""Plan Phase 1 links: owner-register crosswalk and test-type inventory.

Does not call the assistant and does not rewrite v0 or v1.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE0 = ROOT / "evaluation" / "pms-ai" / "phase0"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_owner_crosswalk_matches_the_derivation_report() -> None:
    module = _module(PHASE0 / "map_owner_register.py", "map_owner_register")
    built = module.build()
    assert _load(PHASE0 / "owner_register_map.json") == built
    assert (PHASE0 / "OWNER_REGISTER_MAP.md").read_text(encoding="utf-8") == module.render(built)
    report = _load(PHASE0 / "derivation_report.json")
    assert built["pending_before"] == 190
    assert built["filled_count"] == 18
    assert built["still_pending_count"] == 172
    assert built["derivation_status"] == "partial"
    assert {row["reason"] for row in built["rows"]} == set(report["still_pending_by_reason"])
    assert sum(row["count"] for row in built["rows"]) == 172
    statuses = {row["evidence_status"] for row in built["rows"]}
    assert statuses <= {"verified", "verified no data", "partial", "blocked", "not applicable"}
    assert any(row["match"] == "none" for row in built["rows"])
    assert built["fills"]["joiner_flag"]["evidence_status"] == "verified no data"


def test_test_type_inventory_matches_the_script() -> None:
    module = _module(PHASE0 / "inventory_test_types.py", "inventory_test_types")
    built = module.build()
    assert _load(PHASE0 / "test_type_inventory.json") == built
    assert (PHASE0 / "TEST_TYPE_INVENTORY.md").read_text(encoding="utf-8") == module.render(built)
    paths = [item["path"] for item in built["tests"]]
    assert "Backend/tests/test_pms_ai_phase0_eval_schema.py" in paths
    assert "Backend/tests/test_pms_ai_phase0_derivation.py" in paths
    assert "Backend/tests/test_ai_booking_count_parity.py" in paths
    assert "Backend/tests/test_local_assistant_exploration.py" in paths
    by_path = {item["path"]: item for item in built["tests"]}
    assert by_path["Backend/tests/test_pms_ai_phase0_eval_schema.py"]["labels"] == ["synthetic"]
    assert by_path["Backend/tests/test_pms_ai_phase0_derivation.py"]["labels"] == ["source-parity"]
    assert "mocked" in by_path["Backend/tests/test_ai_booking_count_parity.py"]["labels"]
    assert "source-parity" not in by_path["Backend/tests/test_ai_booking_count_parity.py"]["labels"]
    live = by_path["Backend/tests/test_local_assistant_exploration.py"]
    assert "live-model" in live["labels"]
    assert "mocked" in live["labels"]
    assert built["files_by_label"]["browser"] == 0
    assert sum(built["files_by_label"].values()) >= built["file_count"]


def test_v0_and_v1_expected_values_are_unchanged() -> None:
    frozen_v0 = _load(PHASE0 / "frozen_v0.json")
    heldout_v0 = _load(PHASE0 / "heldout_v0.json")
    frozen_v1 = _load(PHASE0 / "frozen_v1.json")
    heldout_v1 = _load(PHASE0 / "heldout_v1.json")
    assert frozen_v0["schema_version"] == "pms-ai-phase0-eval-v0"
    assert frozen_v1["schema_version"] == "pms-ai-phase0-eval-v1"
    assert heldout_v1["schema_version"] == "pms-ai-phase0-eval-v1"

    def pending(doc: dict) -> int:
        return sum(
            1
            for case in doc["cases"]
            for item in case["expected_values"]
            if item["value"] == "PENDING"
        )

    assert pending(frozen_v0) + pending(heldout_v0) == 190
    assert pending(frozen_v1) + pending(heldout_v1) == 172
