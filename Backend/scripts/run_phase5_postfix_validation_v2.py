"""Run a versioned Phase 5 deterministic or bounded live synthetic validation.

The 80-turn versioned fixture and its original predecessor are immutable inputs.
The metadata/unit contract is shared with postfix contract v1; the current
application sources and this runner are separately hashed in each result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "Backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts import run_phase5_postfix_offline_v1 as contract_v1


RUN_ID = "pms-ai-phase5-postfix-validation-v2"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mode_paths(mode: str) -> tuple[Path, Path]:
    stem = f"phase5_postfix_{mode}_v2"
    directory = BACKEND_DIR / "scripts"
    return directory / f"{stem}.json", directory / f"{stem}.manifest.json"


def _verify_inputs() -> tuple[str, str, str]:
    contract_v1._verify_frozen_inputs()
    contract_v1.contract.load_frozen_inputs()
    fixture_path = contract_v1.POSTFIX_FIXTURE_PATH
    freeze_manifest_path = contract_v1.POSTFIX_FREEZE_MANIFEST_PATH
    fixture_hash = _sha256_file(fixture_path)
    freeze_manifest_hash = _sha256_file(freeze_manifest_path)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    freeze_manifest = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    reference_evaluator_hash = _sha256_file(Path(contract_v1.evaluator.__file__).resolve())
    if fixture_hash != freeze_manifest.get("fixture_sha256"):
        raise ValueError("Versioned fixture hash does not match its manifest")
    if freeze_manifest.get("runner_sha256") != reference_evaluator_hash:
        raise ValueError("Versioned fixture does not identify the current reference evaluator")
    if fixture.get("freeze_manifest") != contract_v1.POSTFIX_FREEZE_MANIFEST_NAME:
        raise ValueError("Versioned fixture points to an unexpected freeze manifest")
    if freeze_manifest.get("source_data_sha256") != contract_v1.contract.SOURCE_DATA_SHA256:
        raise ValueError("Versioned fixture source data hash changed")
    return fixture_hash, freeze_manifest_hash, reference_evaluator_hash


def _prepare_result(result: dict[str, Any], runner_hash: str, reference_hash: str, mode: str) -> None:
    result["reference_evaluator_sha256"] = result["runner_sha256"]
    result["runner_sha256"] = runner_hash
    result["run_id"] = RUN_ID
    result["contract_version"] = contract_v1.CONTRACT_VERSION
    result["run_bound"] = {"max_turns": 80, "actual_turns": result.get("prompt_count")}
    result["actual_cost_status"] = (
        "unknown"
        if int(result["summary"]["overall"].get("total_provider_calls", 0)) > 0
        and float(result["summary"]["overall"].get("total_estimated_cost_usd", 0.0)) == 0.0
        else "not_applicable"
        if int(result["summary"]["overall"].get("total_provider_calls", 0)) == 0
        else "reported"
    )
    result["summary"]["overall"]["actual_cost_status"] = result["actual_cost_status"]
    result["rescore_audit"] = {
        "raw_failures_preserved": True,
        "normalized_turns": sum(
            bool(value.get("semantic_normalizations") or value.get("critical_normalizations"))
            for value in contract_v1._AUDIT.values()
        ),
        "turns": contract_v1._AUDIT,
    }
    for row in result["results"]:
        audit = contract_v1._AUDIT.get(str(row["turn_id"]), {})
        row["raw_semantic_failures"] = audit.get("raw_semantic_failures", row["semantic_failures"])
        row["raw_critical_failures"] = audit.get("raw_critical_failures", row["critical_failures"])
        row["normalizations"] = [
            *(audit.get("semantic_normalizations") or []),
            *(audit.get("critical_normalizations") or []),
        ]
    result["mode"] = mode


def run(mode: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if mode not in {"deterministic", "live"}:
        raise ValueError("mode must be deterministic or live")
    fixture_hash, freeze_manifest_hash, reference_hash = _verify_inputs()
    result_path, manifest_path = _mode_paths(mode)
    if result_path.exists() or manifest_path.exists():
        raise FileExistsError(f"Versioned {mode} result already exists; refusing to overwrite it")

    evaluator = contract_v1.evaluator
    contract_v1._AUDIT.clear()
    evaluator.validate_turn_response = contract_v1._validate_turn
    evaluator.validate_critical_evidence = contract_v1._validate_critical
    try:
        result = evaluator.evaluate_unseen_dataset(
            mode=mode,
            fixture_name=contract_v1.POSTFIX_FIXTURE_NAME,
        )
    finally:
        evaluator.validate_turn_response = contract_v1._BASE_VALIDATE_TURN
        evaluator.validate_critical_evidence = contract_v1._BASE_VALIDATE_CRITICAL

    if result.get("fixture_sha256") != fixture_hash:
        raise ValueError("Evaluator result fixture hash differs from the versioned input")
    if result.get("runner_sha256") != reference_hash:
        raise ValueError("Evaluator result runner hash differs from the versioned manifest")
    if result.get("prompt_count") != 80 or result.get("conversation_count") != 20:
        raise ValueError("Run did not evaluate exactly 20 synthetic conversations / 80 turns")

    runner_hash = _sha256_file(Path(__file__).resolve())
    application_hash = contract_v1._application_source_sha256()
    validator_harness_hash = _sha256_file(Path(contract_v1.__file__).resolve())
    contract_helper_hash = _sha256_file(Path(contract_v1.contract.__file__).resolve())
    _prepare_result(result, runner_hash, reference_hash, mode)
    result["validator_harness_sha256"] = validator_harness_hash
    result["contract_helper_sha256"] = contract_helper_hash
    result["manifest_path"] = str(manifest_path.relative_to(REPO_ROOT))
    result_bytes = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    result_hash = hashlib.sha256(result_bytes).hexdigest()
    overall = result["summary"]["overall"]
    manifest = {
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "mode": mode,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runner": "Backend/scripts/run_phase5_postfix_validation_v2.py",
        "runner_sha256": runner_hash,
        "contract_version": contract_v1.CONTRACT_VERSION,
        "validator_harness_sha256": validator_harness_hash,
        "contract_helper_sha256": contract_helper_hash,
        "reference_evaluator": "Backend/scripts/run_unseen_eval.py",
        "reference_evaluator_sha256": reference_hash,
        "application_source_sha256": application_hash,
        "method": "current application code; versioned metadata/unit validator; synthetic in-memory data only",
        "run_bound": {"max_turns": 80, "actual_turns": result["prompt_count"]},
        "versioned_fixture": {
            "path": f"Backend/tests/fixtures/{contract_v1.POSTFIX_FIXTURE_NAME}",
            "sha256": fixture_hash,
            "freeze_manifest_path": f"Backend/tests/fixtures/{contract_v1.POSTFIX_FREEZE_MANIFEST_NAME}",
            "freeze_manifest_sha256": freeze_manifest_hash,
        },
        "original_frozen_inputs": {
            "fixture_sha256": contract_v1.EXPECTED_FIXTURE_SHA256,
            "freeze_manifest_sha256": contract_v1.EXPECTED_FREEZE_MANIFEST_SHA256,
            "first_run_outputs_unchanged": True,
        },
        "source_data_sha256": result["source_data_sha256"],
        "thresholds_unchanged": result["freeze_requirements"],
        "contract_rules": [
            "Use operation_kind_v2/requested_parts for legacy intent metadata only when supported; compare_periods maps to trend only when frozen minimum-period and movement-evidence checks pass.",
            "Correct legacy metric metadata only when a recorded model-led tool metric argument and matching typed evidence both support the frozen expected metric.",
            "Allow count/bookings/calls/leads/claims unit labels only for a raw catalog metric whose declared unit is in that count family; preserve source evidence unchanged.",
            "Keep catalog-guarded ratio_0_1-to-display-% comparison from the reference evaluator.",
            "Do not normalize outcomes, capability, content, period mentions, scope, identity, unit dimensions, source links, authorization, tools, or evidence absence.",
            "Keep raw semantic and critical failures in each row and list every applied normalization.",
        ],
        "provider_usage": {
            "calls": overall.get("total_provider_calls", 0),
            "call_attempts": overall.get("total_provider_call_attempts", 0),
            "input_tokens": overall.get("total_input_tokens", 0),
            "output_tokens": overall.get("total_output_tokens", 0),
            "reported_estimated_cost_usd": overall.get("total_estimated_cost_usd", 0.0),
            "actual_cost_status": result["actual_cost_status"],
            "fallback_turns": overall.get("fallback_turns", 0),
        },
        "quality_gate": result["quality_gate"],
        "result_path": str(result_path.relative_to(REPO_ROOT)),
        "result_sha256": result_hash,
    }
    result_path.write_bytes(result_bytes)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest, result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("deterministic", "live"), default="deterministic")
    args = parser.parse_args()
    manifest, result = run(args.mode)
    print(json.dumps({
        "run_id": RUN_ID,
        "mode": result["mode"],
        "contract_version": result["contract_version"],
        "fixture_sha256": result["fixture_sha256"],
        "runner_sha256": result["runner_sha256"],
        "quality_gate": result["quality_gate"],
        "summary": {key: value for key, value in result["summary"]["overall"].items() if key != "failures"},
        "normalization_count": result["rescore_audit"]["normalized_turns"],
        "actual_cost_status": result["actual_cost_status"],
        "manifest_path": str(_mode_paths(result["mode"])[1].relative_to(REPO_ROOT)),
        "manifest_sha256": _sha256_file(_mode_paths(result["mode"])[1]),
        "result_path": str(_mode_paths(result["mode"])[0].relative_to(REPO_ROOT)),
        "result_sha256": manifest["result_sha256"],
    }, ensure_ascii=False, indent=2))
