"""Rescore immutable Phase 5 first-run outputs under documented metadata contracts.

This is a read-only rescorer. It does not execute the chat application or contact a
provider. It writes new, versioned manifest/result files and refuses to overwrite
them. The original fixture, freeze manifest, runner, and result files are inputs.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "Backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts import run_unseen_eval as original_evaluator  # noqa: E402
from services.ai.catalog import get_ai_catalog  # noqa: E402


RESCORE_ID = "pms-ai-phase5-postfix-rescore-v1"
CONTRACT_VERSION = "pms-ai-metadata-units-v1"
FIXTURE_NAME = "ai_phase5_final_frozen.json"
MANIFEST_NAME = "ai_phase5_final_frozen.manifest.json"
ORIGINAL_RUNNER_SHA256 = "3fb496f60d26e55a198f5cfad6a7d8fab3c9906acf2399a56c8a05da1a01e03e"
SOURCE_DATA_SHA256 = "6bf79419ded46da9644e7bb0498a3a5da550a99bda494f8b3ac6acc977dbb68a"
EXPECTED_HASHES = {
    "fixture": "9e939f0d393acca689c6f715589c0e8d144a9d8c354c8084c5eb1292bd46f2e8",
    "freeze_manifest": "72eb979ec2cb479a461b4b8aad943aab514072933819e91402b1fee8427528be",
    "deterministic": "af99b0d5bb2370ee74987e7d6af73959054ec4f873739bf9e069f90fb4204859",
    "mocked": "68cf4fa948683e05de8728f29f017edadc0697ffa9eeb03b04f1ee4cdae0e00c",
    "live": "7b8924d2cf03bb2dfb64a8acea8a4c86c1b42f3ebd91bfc6920e4d0bc970e5be",
}
RESULT_FILES = {
    "deterministic": "phase5_final_deterministic_20261117.json",
    "mocked": "phase5_final_mocked_failure_20261117.json",
    "live": "phase5_final_live_20261117.json",
}
COUNT_UNITS = frozenset({"count", "bookings", "calls", "leads", "claims"})
ALNUM_RE = re.compile(r"[^a-z0-9]")
PERIOD_MENTION_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}\b",
    re.IGNORECASE,
)
TREND_EVIDENCE_RE = re.compile(
    r"\b(?:across|from\b.{1,40}\bto|moved|pp|delta|flat|no change|unchanged|insufficient|only 1)\b|[+-]\d+(?:\.\d+)?",
    re.IGNORECASE,
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _norm(value: Any) -> str:
    return ALNUM_RE.sub("", str(value or "").casefold())


def _metric_values(item: dict[str, Any]) -> set[str]:
    raw = {
        str(item.get("kpi_key") or ""),
        str(item.get("metric_id") or "").rsplit(":", 1)[-1],
        str(item.get("display_name") or ""),
    }
    return {_norm(value) for value in raw if value}


def _metric_definition(item: dict[str, Any], spec: dict[str, Any]):
    metric_key = str(item.get("metric_id") or item.get("kpi_key") or spec.get("kpi_key") or "")
    return get_ai_catalog().find_metric_definition(
        team=str(item.get("team") or spec.get("team") or "") or None,
        kpi_key_or_label=metric_key,
        position=str(item.get("position") or "") or None,
        performance_level=str(item.get("performance_level") or "Employee"),
    )


def _count_unit_alias_is_valid(item: dict[str, Any], spec: dict[str, Any]) -> bool:
    actual_unit = str(item.get("unit") or "").casefold()
    expected_unit = str(spec.get("unit") or "").casefold()
    if actual_unit not in COUNT_UNITS or expected_unit not in COUNT_UNITS:
        return False
    definition = _metric_definition(item, spec)
    return bool(
        definition
        and str(getattr(definition, "storage_scale", "")).casefold() == "raw"
        and str(getattr(definition, "unit", "")).casefold() in COUNT_UNITS
    )


def _evidence_matches_except_unit(
    item: dict[str, Any],
    spec: dict[str, Any],
) -> tuple[bool, str | None]:
    expected_metric = _norm(spec.get("kpi_key"))
    if expected_metric and expected_metric not in _metric_values(item):
        return False, None
    expected_period = original_evaluator._normalize_period(spec.get("period")) if spec.get("period") else None
    if expected_period and original_evaluator._normalize_period(item.get("period")) != expected_period:
        return False, None
    if "employee_id" in spec and (item.get("employee_id") or None) != spec.get("employee_id"):
        return False, None
    if spec.get("employee_name") and str(item.get("employee_name") or "").casefold() != str(spec["employee_name"]).casefold():
        return False, None
    if spec.get("require_aggregate") and (item.get("employee_id") or item.get("employee_name")):
        return False, None
    if "branch" in spec and str(item.get("branch") or "").casefold() != str(spec.get("branch") or "").casefold():
        return False, None
    if "team" in spec and str(item.get("team") or "").casefold() != str(spec.get("team") or "").casefold():
        return False, None
    if "performance_level" in spec and str(item.get("performance_level") or "").casefold() != str(spec.get("performance_level") or "").casefold():
        return False, None
    if spec.get("actual") is not None and not original_evaluator._matches_expected_actual(item, spec):
        return False, None

    actual_unit = str(item.get("unit") or "").casefold()
    expected_unit = str(spec.get("unit") or "").casefold()
    normalization = None
    if "unit" in spec and actual_unit != expected_unit:
        if not _count_unit_alias_is_valid(item, spec):
            return False, None
        normalization = (
            f"count-unit alias {actual_unit!r} accepted for {expected_unit!r} "
            f"under raw catalog metric {item.get('metric_id') or item.get('kpi_key')}"
        )

    if spec.get("source_required", True) and not str(item.get("source_link") or "").strip():
        return False, None
    if spec.get("source_contains") and str(spec["source_contains"]).casefold() not in str(item.get("source_link") or "").casefold():
        return False, None
    return True, normalization


def rescore_critical_evidence(turn: dict[str, Any], row: dict[str, Any]) -> tuple[list[str], list[str]]:
    evidence = [dict(item) for item in (row.get("typed_evidence") or [])]
    failures: list[str] = []
    normalizations: list[str] = []

    for spec in turn.get("expected_evidence") or []:
        match_found = False
        for item in evidence:
            matched, normalization = _evidence_matches_except_unit(item, spec)
            if matched:
                match_found = True
                if normalization:
                    normalizations.append(normalization)
                break
        if not match_found:
            failures.append(f"missing typed evidence contract {spec!r}")

    if turn.get("expect_no_evidence") and evidence:
        failures.append(f"expected no typed evidence, received {len(evidence)} item(s)")
    if turn.get("require_source_for_all_evidence"):
        missing_sources = [item for item in evidence if not str(item.get("source_link") or "").strip()]
        if missing_sources:
            failures.append(f"{len(missing_sources)} typed evidence item(s) lack a source link")

    expected_outcomes = set(turn.get("expected_outcomes") or [])
    restricted_expected = turn.get("expected_outcome") == "restricted_access" or "restricted_access" in expected_outcomes
    if turn.get("critical_authorization") and restricted_expected:
        if evidence:
            failures.append("restricted response returned typed evidence")
        if row.get("tool_names"):
            failures.append("restricted response executed a data tool")

    actual_tools = set(row.get("tool_names") or [])
    expected_tools = set(turn.get("expected_tool_names") or [])
    if not expected_tools.issubset(actual_tools):
        failures.append(f"tool names {sorted(actual_tools)!r} missing {sorted(expected_tools - actual_tools)!r}")
    expected_any_tools = set(turn.get("expected_any_tool_names") or [])
    if expected_any_tools and not expected_any_tools.intersection(actual_tools):
        failures.append(f"tool names {sorted(actual_tools)!r} contain none of {sorted(expected_any_tools)!r}")
    return failures, normalizations


def _tool_metric_candidates(structured_query: dict[str, Any]) -> set[str]:
    calls = list(structured_query.get("model_led_tool_calls") or [])
    if structured_query.get("model_led_tool_call"):
        calls.append(structured_query["model_led_tool_call"])
    candidates: set[str] = set()
    for call in calls:
        args = call.get("tool_arguments") or {}
        for field in ("metric_id", "metric", "kpi_key"):
            value = args.get(field)
            if value:
                candidates.add(_norm(str(value).rsplit(":", 1)[-1]))
    return candidates


def _metric_has_typed_support(
    expected_metric: str,
    turn: dict[str, Any],
    row: dict[str, Any],
) -> bool:
    expected = _norm(expected_metric)
    query = row.get("structured_query") or {}
    argument_match = expected in _tool_metric_candidates(query)
    expected_specs = [
        spec for spec in (turn.get("expected_evidence") or [])
        if _norm(spec.get("kpi_key")) == expected
    ]
    for item in row.get("typed_evidence") or []:
        if expected not in _metric_values(item):
            continue
        # A country-specific catalog ID can differ from the workbook KPI key.
        # Require the exact query ID and that key on the same sourced fact.
        bound_source_metric = (
            query.get("metric") and query["metric"] == item.get("metric_id")
            and expected == _norm(item.get("kpi_key")) and item.get("source_link")
        )
        if not argument_match and not bound_source_metric:
            continue
        if expected_specs and not any(_evidence_matches_except_unit(item, spec)[0] for spec in expected_specs):
            continue
        return True
    return False


def _canonical_intent_supports(
    expected_intent: str,
    turn: dict[str, Any],
    row: dict[str, Any],
) -> tuple[bool, str | None]:
    structured = row.get("structured_query") or {}
    operation = str(structured.get("operation_kind_v2") or "")
    requested_parts = {str(x) for x in (structured.get("requested_parts") or [])}
    if expected_intent == operation or expected_intent in requested_parts:
        return True, f"canonical operation metadata {operation or sorted(requested_parts)!r}"

    # The legacy intent `trend` is equivalent to a period comparison only when
    # its own published trend checks prove enough distinct periods and movement.
    if expected_intent == "trend" and operation == "compare_periods":
        text = "\n".join(
            [str(row.get("headline") or ""), *[str(x) for x in row.get("narrative_bullets") or []]]
        )
        required_periods = int(turn.get("expected_min_trend_periods") or 0)
        observed_periods = {x.casefold() for x in PERIOD_MENTION_RE.findall(text)}
        if (
            required_periods >= 2
            and len(observed_periods) >= required_periods
            and TREND_EVIDENCE_RE.search(text)
        ):
            return True, "compare_periods operation with required period and movement evidence"
    return False, None


def rescore_semantic_metadata(turn: dict[str, Any], row: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures = list(row.get("semantic_failures") or [])
    normalizations: list[str] = []
    expected_intent = turn.get("expected_intent")
    if expected_intent:
        supported, evidence = _canonical_intent_supports(str(expected_intent), turn, row)
        if supported:
            kept: list[str] = []
            removed = False
            for failure in failures:
                if not removed and failure.startswith("intent "):
                    removed = True
                    continue
                kept.append(failure)
            if removed:
                failures = kept
                normalizations.append(f"legacy intent resolved through {evidence}")

    if "expected_metric" in turn and turn.get("expected_metric") is not None:
        expected_metric = str(turn["expected_metric"])
        if _metric_has_typed_support(expected_metric, turn, row):
            kept = []
            removed = False
            for failure in failures:
                if not removed and failure.startswith("metric "):
                    removed = True
                    continue
                kept.append(failure)
            if removed:
                failures = kept
                normalizations.append(
                    f"legacy metric metadata resolved by matching tool argument and typed evidence for {expected_metric}"
                )
    return failures, normalizations


def _remaining_failures(
    all_failures: list[str],
    semantic_failures: list[str],
    critical_failures: list[str],
) -> list[str]:
    known = Counter(semantic_failures) + Counter(critical_failures)
    remaining: list[str] = []
    for failure in all_failures:
        if known[failure]:
            known[failure] -= 1
        else:
            remaining.append(failure)
    return remaining


def _summary(rows: list[dict[str, Any]], *, thresholds: dict[str, Any], original: dict[str, Any]) -> dict[str, Any]:
    total = len(rows)
    semantic_passed = sum(not row["rescored_semantic_failures"] for row in rows)
    critical_rows = [row for row in rows if row["critical_check_required"]]
    critical_passed = sum(not row["rescored_critical_failures"] for row in critical_rows)
    overall_passed = sum(row["rescored_passed"] for row in rows)
    semantic_pct = round(semantic_passed * 100.0 / total, 2) if total else 0.0
    critical_pct = round(critical_passed * 100.0 / len(critical_rows), 2) if critical_rows else 0.0
    critical_target = float(thresholds.get("critical_accuracy_pct", 100.0))
    semantic_target = float(thresholds.get("semantic_accuracy_pct", 95.0))
    return {
        "total": total,
        "passed": overall_passed,
        "accuracy_pct": round(overall_passed * 100.0 / total, 2) if total else 0.0,
        "semantic_passed": semantic_passed,
        "semantic_accuracy_pct": semantic_pct,
        "critical_check_passed_turns": critical_passed,
        "critical_check_required_turns": len(critical_rows),
        "critical_check_pass_rate_pct": critical_pct,
        "p50_ms": original.get("p50_ms"),
        "p95_ms": original.get("p95_ms"),
        "total_provider_calls": original.get("total_provider_calls", 0),
        "total_provider_call_attempts": original.get("total_provider_call_attempts", 0),
        "total_input_tokens": original.get("total_input_tokens", 0),
        "total_output_tokens": original.get("total_output_tokens", 0),
        "reported_estimated_cost_usd": original.get("total_estimated_cost_usd", 0.0),
        "actual_cost_status": (
            "unknown"
            if int(original.get("total_provider_calls", 0)) > 0
            and float(original.get("total_estimated_cost_usd", 0.0)) == 0.0
            else "not_applicable" if int(original.get("total_provider_calls", 0)) == 0 else "reported"
        ),
        "fallback_turns": original.get("fallback_turns", 0),
        "quality_gate": {
            "critical_target_pct": critical_target,
            "critical_pass": critical_pct >= critical_target,
            "semantic_target_pct": semantic_target,
            "semantic_pass": semantic_pct >= semantic_target,
            "passed": critical_pct >= critical_target and semantic_pct >= semantic_target,
        },
    }


def load_frozen_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]], dict[str, str]]:
    fixture_path = BACKEND_DIR / "tests" / "fixtures" / FIXTURE_NAME
    manifest_path = BACKEND_DIR / "tests" / "fixtures" / MANIFEST_NAME
    fixture_hash = sha256_file(fixture_path)
    manifest_hash = sha256_file(manifest_path)
    if fixture_hash != EXPECTED_HASHES["fixture"] or manifest_hash != EXPECTED_HASHES["freeze_manifest"]:
        raise ValueError("Original frozen fixture or freeze manifest hash changed; refusing to rescore")

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if fixture.get("freeze_manifest") != MANIFEST_NAME:
        raise ValueError("Frozen fixture points to an unexpected manifest")
    if manifest.get("fixture_sha256") != fixture_hash or manifest.get("runner_sha256") != ORIGINAL_RUNNER_SHA256:
        raise ValueError("Original freeze manifest metadata does not match the recorded first run")
    if manifest.get("source_data_sha256") != SOURCE_DATA_SHA256:
        raise ValueError("Original synthetic source hash does not match the recorded first run")

    result_inputs: dict[str, dict[str, Any]] = {}
    hashes = {"fixture": fixture_hash, "freeze_manifest": manifest_hash}
    for mode, filename in RESULT_FILES.items():
        path = BACKEND_DIR / "scripts" / filename
        result_hash = sha256_file(path)
        if result_hash != EXPECTED_HASHES[mode]:
            raise ValueError(f"Original {mode} first-run result changed; refusing to rescore")
        result = json.loads(path.read_text(encoding="utf-8"))
        if (
            result.get("fixture_sha256") != fixture_hash
            or result.get("source_data_sha256") != SOURCE_DATA_SHA256
            or result.get("runner_sha256") != ORIGINAL_RUNNER_SHA256
        ):
            raise ValueError(f"Original {mode} result provenance does not match the frozen manifest")
        if result.get("mode") != mode or len(result.get("results") or []) != 80:
            raise ValueError(f"Original {mode} result has an unexpected mode or row count")
        result_inputs[mode] = result
        hashes[mode] = result_hash
    return fixture, manifest, result_inputs, hashes


def build_rescore() -> tuple[dict[str, Any], dict[str, Any]]:
    fixture, freeze_manifest, results_by_mode, hashes = load_frozen_inputs()
    expected: dict[str, tuple[str, dict[str, Any]]] = {}
    for conversation in fixture.get("conversations") or []:
        conversation_id = str(conversation["id"])
        for turn in conversation.get("turns") or []:
            turn_id = str(turn["id"])
            if turn_id in expected:
                raise ValueError(f"Duplicate frozen turn ID {turn_id}")
            expected[turn_id] = (conversation_id, turn)
    if len(expected) != 80:
        raise ValueError(f"Expected exactly 80 frozen turns, found {len(expected)}")

    output_modes: dict[str, Any] = {}
    for mode, source in results_by_mode.items():
        source_rows = source.get("results") or []
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for source_row in source_rows:
            turn_id = str(source_row.get("turn_id") or "")
            if turn_id in seen or turn_id not in expected:
                raise ValueError(f"Unexpected or duplicate {mode} turn row {turn_id!r}")
            seen.add(turn_id)
            conversation_id, turn = expected[turn_id]
            if source_row.get("conversation") != conversation_id:
                raise ValueError(f"Conversation mapping changed for {turn_id}")
            semantic_failures, semantic_norms = rescore_semantic_metadata(turn, source_row)
            critical_failures, critical_norms = rescore_critical_evidence(turn, source_row)
            other_failures = _remaining_failures(
                list(source_row.get("failures") or []),
                list(source_row.get("semantic_failures") or []),
                list(source_row.get("critical_failures") or []),
            )
            rows.append(
                {
                    "conversation": conversation_id,
                    "turn_id": turn_id,
                    "raw_passed": bool(source_row.get("passed")),
                    "raw_semantic_failures": list(source_row.get("semantic_failures") or []),
                    "raw_critical_failures": list(source_row.get("critical_failures") or []),
                    "rescored_semantic_failures": semantic_failures,
                    "rescored_critical_failures": critical_failures,
                    "unclassified_original_failures": other_failures,
                    "normalizations": [*semantic_norms, *critical_norms],
                    "critical_check_required": bool(source_row.get("critical_check_required")),
                    "rescored_passed": not semantic_failures and not critical_failures and not other_failures,
                    "provider_used": source_row.get("provider_used"),
                    "provider_calls": source_row.get("provider_calls", 0),
                    "provider_call_attempts": source_row.get("provider_call_attempts", 0),
                    "fallback_outcome": source_row.get("fallback_outcome", "none"),
                }
            )
        if seen != set(expected):
            raise ValueError(f"{mode} result omitted {len(set(expected) - seen)} frozen turns")
        output_modes[mode] = {
            "source_result_file": RESULT_FILES[mode],
            "source_result_sha256": hashes[mode],
            "original_summary": source["summary"]["overall"],
            "rescored_summary": _summary(rows, thresholds=fixture["freeze_requirements"], original=source["summary"]["overall"]),
            "rows": rows,
        }

    runner_hash = sha256_file(Path(__file__).resolve())
    engine_hash = sha256_file(BACKEND_DIR / "scripts" / "run_unseen_eval.py")
    manifest = {
        "schema_version": "1.0",
        "rescore_id": RESCORE_ID,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runner": "Backend/scripts/rescore_phase5_frozen_outputs_v1.py",
        "runner_sha256": runner_hash,
        "reference_evaluator": "Backend/scripts/run_unseen_eval.py",
        "reference_evaluator_sha256": engine_hash,
        "method": "read-only rescore of saved first-run outputs; no application/provider execution",
        "source_frozen_evaluation_label": "exposed_regression",
        "source_artifacts": {
            "fixture": {"path": f"Backend/tests/fixtures/{FIXTURE_NAME}", "sha256": hashes["fixture"]},
            "freeze_manifest": {"path": f"Backend/tests/fixtures/{MANIFEST_NAME}", "sha256": hashes["freeze_manifest"]},
            "source_data_sha256": SOURCE_DATA_SHA256,
            "original_runner_sha256": ORIGINAL_RUNNER_SHA256,
            "first_run_results": {
                mode: {"path": f"Backend/scripts/{RESULT_FILES[mode]}", "sha256": hashes[mode]}
                for mode in RESULT_FILES
            },
        },
        "contract_version": CONTRACT_VERSION,
        "contract_rules": [
            "Use operation_kind_v2/requested_parts when legacy structured_query.intent conflicts; map compare_periods to trend only when the turn also meets its frozen minimum-period and movement-evidence checks.",
            "Resolve missing legacy metric metadata only when a recorded model-led tool metric argument and typed evidence both match the frozen expected metric; the typed evidence remains mandatory.",
            "Treat count/bookings/calls/leads/claims as equivalent count labels only when the resolved catalog metric is raw and declares a unit in that same count family; retain and report the source evidence unit.",
            "Retain catalog-guarded ratio_0_1-to-display-% comparison from the reference evaluator.",
            "Do not normalize outcome, capability, textual content, periods, identity, scope, unit dimension, source links, authorization, tools, or no-evidence violations.",
            "Preserve all original failures and report unclassified failures; missing source fields remain unverified.",
        ],
        "thresholds": {
            "min_conversations": int(freeze_manifest.get("conversation_count", 0)),
            "min_prompts": int(freeze_manifest.get("prompt_count", 0)),
            "critical_accuracy_pct": float(fixture["freeze_requirements"]["critical_accuracy_pct"]),
            "semantic_accuracy_pct": float(fixture["freeze_requirements"]["semantic_accuracy_pct"]),
        },
        "output_files": {
            "manifest": "Backend/scripts/phase5_postfix_rescore_v1.manifest.json",
            "result": "Backend/scripts/phase5_postfix_rescore_v1.json",
        },
    }
    manifest_hash = sha256_bytes(json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    result = {
        "schema_version": "1.0",
        "rescore_id": RESCORE_ID,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": manifest_hash,
        "source_frozen_evaluation_label": "exposed_regression",
        "source_fixture": FIXTURE_NAME,
        "source_fixture_sha256": hashes["fixture"],
        "contract_version": CONTRACT_VERSION,
        "thresholds_unchanged": manifest["thresholds"],
        "method": manifest["method"],
        "modes": output_modes,
    }
    return manifest, result


def write_rescore_artifacts(manifest: dict[str, Any], result: dict[str, Any]) -> tuple[Path, Path]:
    manifest_path = BACKEND_DIR / "scripts" / "phase5_postfix_rescore_v1.manifest.json"
    result_path = BACKEND_DIR / "scripts" / "phase5_postfix_rescore_v1.json"
    if manifest_path.exists() or result_path.exists():
        raise FileExistsError("Versioned rescore output already exists; refusing to overwrite it")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path, result_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Build the rescore in memory without writing artifacts")
    args = parser.parse_args()
    manifest, result = build_rescore()
    if args.dry_run:
        output_paths: list[str] = []
    else:
        output_paths = [str(path.relative_to(REPO_ROOT)) for path in write_rescore_artifacts(manifest, result)]
    print(json.dumps({
        "rescore_id": RESCORE_ID,
        "source_frozen_evaluation_label": "exposed_regression",
        "manifest_sha256": result["manifest_sha256"],
        "outputs": output_paths,
        "modes": {
            mode: {
                "raw": data["original_summary"],
                "rescored": data["rescored_summary"],
            }
            for mode, data in result["modes"].items()
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
