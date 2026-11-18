"""Run the frozen Phase 5 fixture against current code under metadata contract v1.

This versioned harness keeps the original evaluator and frozen inputs intact. It
executes all turns in deterministic mode, then applies only the audited semantic
metadata and catalog-governed count-unit corrections from the companion rescorer.
"""

from __future__ import annotations

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

from scripts import rescore_phase5_frozen_outputs_v1 as contract  # noqa: E402
from scripts import run_unseen_eval as evaluator  # noqa: E402


RUN_ID = "pms-ai-phase5-postfix-offline-v1"
CONTRACT_VERSION = contract.CONTRACT_VERSION
FIXTURE_NAME = "ai_phase5_final_frozen.json"
FIXTURE_PATH = BACKEND_DIR / "tests" / "fixtures" / FIXTURE_NAME
FREEZE_MANIFEST_PATH = BACKEND_DIR / "tests" / "fixtures" / "ai_phase5_final_frozen.manifest.json"
POSTFIX_FIXTURE_NAME = "ai_phase5_postfix_offline_v1.json"
POSTFIX_FREEZE_MANIFEST_NAME = "ai_phase5_postfix_offline_v1.manifest.json"
POSTFIX_FIXTURE_PATH = BACKEND_DIR / "tests" / "fixtures" / POSTFIX_FIXTURE_NAME
POSTFIX_FREEZE_MANIFEST_PATH = BACKEND_DIR / "tests" / "fixtures" / POSTFIX_FREEZE_MANIFEST_NAME
EXPECTED_FIXTURE_SHA256 = contract.EXPECTED_HASHES["fixture"]
EXPECTED_FREEZE_MANIFEST_SHA256 = contract.EXPECTED_HASHES["freeze_manifest"]
ORIGINAL_FROZEN_RUNNER_SHA256 = contract.ORIGINAL_RUNNER_SHA256
RESULT_PATH = BACKEND_DIR / "scripts" / "phase5_postfix_deterministic_v1.json"
MANIFEST_PATH = BACKEND_DIR / "scripts" / "phase5_postfix_deterministic_v1.manifest.json"

_BASE_VALIDATE_TURN = evaluator.validate_turn_response
_BASE_VALIDATE_CRITICAL = evaluator.validate_critical_evidence
_AUDIT: dict[str, dict[str, Any]] = {}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _application_source_sha256() -> str:
    roots = [BACKEND_DIR / name for name in ("api", "models", "repositories", "services", "utils")]
    digest = hashlib.sha256()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            relative = path.relative_to(BACKEND_DIR).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(4, "big"))
            digest.update(relative)
            payload = path.read_bytes()
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
    return digest.hexdigest()


def _response_row(resp: Any, semantic_failures: list[str] | None = None) -> dict[str, Any]:
    structured = resp.structured_query.model_dump(mode="json") if resp.structured_query else None
    evidence = [item.model_dump(mode="json") for item in (resp.typed_evidence or [])]
    return {
        "semantic_failures": list(semantic_failures or []),
        "structured_query": structured,
        "headline": resp.headline,
        "narrative_bullets": list(resp.narrative_bullets or []),
        "typed_evidence": evidence,
        "tool_names": [tool.tool_name for tool in (resp.tool_calls or [])],
    }


def _validate_turn(turn: dict[str, Any], resp: Any, *, elapsed_ms: float = 0.0) -> list[str]:
    raw_failures = _BASE_VALIDATE_TURN(turn, resp, elapsed_ms=elapsed_ms)
    row = _response_row(resp, raw_failures)
    corrected_failures, normalizations = contract.rescore_semantic_metadata(turn, row)
    entry = _AUDIT.setdefault(str(turn["id"]), {})
    entry["raw_semantic_failures"] = raw_failures
    entry["rescored_semantic_failures"] = corrected_failures
    entry["semantic_normalizations"] = normalizations
    return corrected_failures


def _validate_critical(turn: dict[str, Any], resp: Any) -> list[str]:
    raw_failures = _BASE_VALIDATE_CRITICAL(turn, resp)
    row = _response_row(resp)
    corrected_failures, normalizations = contract.rescore_critical_evidence(turn, row)
    entry = _AUDIT.setdefault(str(turn["id"]), {})
    entry["raw_critical_failures"] = raw_failures
    entry["rescored_critical_failures"] = corrected_failures
    entry["critical_normalizations"] = normalizations
    return corrected_failures


def _verify_frozen_inputs() -> tuple[str, str]:
    fixture_hash = _sha256_file(FIXTURE_PATH)
    manifest_hash = _sha256_file(FREEZE_MANIFEST_PATH)
    if fixture_hash != EXPECTED_FIXTURE_SHA256:
        raise ValueError("Original frozen fixture hash changed; refusing post-fix run")
    if manifest_hash != EXPECTED_FREEZE_MANIFEST_SHA256:
        raise ValueError("Original freeze manifest hash changed; refusing post-fix run")
    original_manifest = json.loads(FREEZE_MANIFEST_PATH.read_text(encoding="utf-8"))
    if original_manifest.get("runner_sha256") != ORIGINAL_FROZEN_RUNNER_SHA256:
        raise ValueError("Original freeze manifest does not identify the original evaluator revision")
    return fixture_hash, manifest_hash


def _prepare_versioned_fixture(original_fixture_hash: str, original_manifest_hash: str) -> tuple[str, str, str]:
    if POSTFIX_FIXTURE_PATH.exists() or POSTFIX_FREEZE_MANIFEST_PATH.exists():
        raise FileExistsError("Versioned post-fix fixture already exists; refusing to overwrite it")
    original_dataset = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    dataset = dict(original_dataset)
    dataset["freeze_manifest"] = POSTFIX_FREEZE_MANIFEST_NAME
    fixture_bytes = (json.dumps(dataset, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fixture_hash = hashlib.sha256(fixture_bytes).hexdigest()
    conversation_count = len(dataset.get("conversations") or [])
    prompt_count = sum(len(conv.get("turns") or []) for conv in dataset.get("conversations") or [])
    reference_hash = _sha256_file(Path(evaluator.__file__).resolve())
    source_manifest = {
        "schema_version": "1.0",
        "fixture": POSTFIX_FIXTURE_NAME,
        "fixture_sha256": fixture_hash,
        "runner_sha256": reference_hash,
        "source_data_sha256": contract.SOURCE_DATA_SHA256,
        "conversation_count": conversation_count,
        "prompt_count": prompt_count,
        "source_frozen_fixture": {
            "path": f"Backend/tests/fixtures/{FIXTURE_NAME}",
            "sha256": original_fixture_hash,
        },
        "source_frozen_manifest": {
            "path": "Backend/tests/fixtures/ai_phase5_final_frozen.manifest.json",
            "sha256": original_manifest_hash,
            "original_runner_sha256": ORIGINAL_FROZEN_RUNNER_SHA256,
        },
        "method": "same immutable 20-conversation/80-turn expectations; versioned manifest points to the current evaluator revision",
    }
    manifest_bytes = (json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    POSTFIX_FIXTURE_PATH.write_bytes(fixture_bytes)
    POSTFIX_FREEZE_MANIFEST_PATH.write_bytes(manifest_bytes)
    return fixture_hash, hashlib.sha256(manifest_bytes).hexdigest(), reference_hash


def run() -> tuple[dict[str, Any], dict[str, Any]]:
    original_fixture_hash, original_manifest_hash = _verify_frozen_inputs()
    if RESULT_PATH.exists() or MANIFEST_PATH.exists():
        raise FileExistsError("Versioned offline result already exists; refusing to overwrite it")
    fixture_hash, freeze_manifest_hash, reference_evaluator_hash = _prepare_versioned_fixture(
        original_fixture_hash, original_manifest_hash
    )

    _AUDIT.clear()
    evaluator.validate_turn_response = _validate_turn
    evaluator.validate_critical_evidence = _validate_critical
    try:
        result = evaluator.evaluate_unseen_dataset(mode="deterministic", fixture_name=POSTFIX_FIXTURE_NAME)
    finally:
        evaluator.validate_turn_response = _BASE_VALIDATE_TURN
        evaluator.validate_critical_evidence = _BASE_VALIDATE_CRITICAL

    if result.get("prompt_count") != 80 or result.get("conversation_count") != 20:
        raise ValueError("Frozen Phase 5 run did not evaluate exactly 20 conversations / 80 turns")
    if result.get("source_data_sha256") != contract.SOURCE_DATA_SHA256:
        raise ValueError("Synthetic source data changed; refusing to publish the result")
    if result.get("fixture_sha256") != fixture_hash:
        raise ValueError("Evaluator fixture hash differs from the frozen input")
    if result.get("runner_sha256") != reference_evaluator_hash:
        raise ValueError("Evaluator runner hash differs from the versioned fixture manifest")

    runner_hash = _sha256_file(Path(__file__).resolve())
    application_hash = _application_source_sha256()
    result["reference_evaluator_sha256"] = result["runner_sha256"]
    result["runner_sha256"] = runner_hash
    result["run_id"] = RUN_ID
    result["contract_version"] = CONTRACT_VERSION
    result["rescore_audit"] = {
        "raw_failures_preserved": True,
        "normalized_turns": sum(bool(value.get("semantic_normalizations") or value.get("critical_normalizations")) for value in _AUDIT.values()),
        "turns": _AUDIT,
    }
    for row in result["results"]:
        audit = _AUDIT.get(str(row["turn_id"]), {})
        row["raw_semantic_failures"] = audit.get("raw_semantic_failures", row["semantic_failures"])
        row["raw_critical_failures"] = audit.get("raw_critical_failures", row["critical_failures"])
        row["normalizations"] = [
            *(audit.get("semantic_normalizations") or []),
            *(audit.get("critical_normalizations") or []),
        ]

    manifest = {
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runner": "Backend/scripts/run_phase5_postfix_offline_v1.py",
        "runner_sha256": runner_hash,
        "contract_version": CONTRACT_VERSION,
        "reference_evaluator": "Backend/scripts/run_unseen_eval.py",
        "reference_evaluator_sha256": reference_evaluator_hash,
        "method": "current application code; deterministic offline execution; versioned semantic and critical metadata validator",
        "fixture": {
            "path": f"Backend/tests/fixtures/{POSTFIX_FIXTURE_NAME}",
            "sha256": fixture_hash,
            "freeze_manifest_path": f"Backend/tests/fixtures/{POSTFIX_FREEZE_MANIFEST_NAME}",
            "freeze_manifest_sha256": freeze_manifest_hash,
        },
        "source_frozen_fixture": {
            "path": f"Backend/tests/fixtures/{FIXTURE_NAME}",
            "sha256": original_fixture_hash,
        },
        "source_frozen_manifest": {
            "path": "Backend/tests/fixtures/ai_phase5_final_frozen.manifest.json",
            "sha256": original_manifest_hash,
            "original_runner_sha256": ORIGINAL_FROZEN_RUNNER_SHA256,
        },
        "source_data_sha256": result["source_data_sha256"],
        "application_source_sha256": application_hash,
        "thresholds_unchanged": result["freeze_requirements"],
        "contract_rules": [
            "Use operation_kind_v2/requested_parts for legacy intent metadata only when supported; compare_periods maps to trend only when frozen minimum-period and movement-evidence checks pass.",
            "Correct legacy metric metadata only when a recorded model-led tool metric argument and matching typed evidence both support the frozen expected metric.",
            "Allow count/bookings/calls/leads/claims unit labels only for a raw catalog metric whose declared unit is in that count family; preserve source evidence unchanged.",
            "Keep catalog-guarded ratio_0_1-to-display-% comparison from the reference evaluator.",
            "Do not normalize outcomes, capability, content, period mentions, scope, identity, unit dimensions, source links, authorization, tools, or evidence absence.",
            "Keep raw semantic and critical failures in each row and list every applied normalization.",
        ],
        "result_path": "Backend/scripts/phase5_postfix_deterministic_v1.json",
        "quality_gate": result["quality_gate"],
        "provider_usage": result["summary"]["overall"],
    }
    result["manifest_path"] = "Backend/scripts/phase5_postfix_deterministic_v1.manifest.json"
    result_bytes = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest["result_sha256"] = hashlib.sha256(result_bytes).hexdigest()
    RESULT_PATH.write_bytes(result_bytes)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest, result


if __name__ == "__main__":
    manifest, result = run()
    overall = result["summary"]["overall"]
    print(json.dumps({
        "run_id": RUN_ID,
        "contract_version": CONTRACT_VERSION,
        "fixture_sha256": result["fixture_sha256"],
        "runner_sha256": result["runner_sha256"],
        "quality_gate": result["quality_gate"],
        "summary": {key: value for key, value in overall.items() if key != "failures"},
        "normalization_count": result["rescore_audit"]["normalized_turns"],
        "manifest_path": str(MANIFEST_PATH.relative_to(REPO_ROOT)),
        "manifest_sha256": _sha256_file(MANIFEST_PATH),
        "result_path": str(RESULT_PATH.relative_to(REPO_ROOT)),
        "result_sha256": manifest["result_sha256"],
    }, ensure_ascii=False, indent=2))
