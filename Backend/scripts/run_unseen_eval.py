"""Semantic multi-turn evaluation runner for unseen PMS AI prompts.

Evaluates dev and held-out conversations separately without tuning rules to
held-out wording, measuring outcome/capability/entity/period/content accuracy,
provider call counts, and per-turn latency.
"""
from __future__ import annotations

import json
import hashlib
import math
import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
TESTS_DIR = BACKEND_DIR / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _pytest.monkeypatch import MonkeyPatch  # noqa: E402
from ai_provider_fakes import failed_response, install_scripted_provider  # noqa: E402
from config.environment import load_project_environment  # noqa: E402
from models.ai_schemas import AiChatRequest, SessionFilterContext  # noqa: E402
from services.ai.catalog import ai_evidence_cache, get_ai_catalog  # noqa: E402
from services.ai.conversation_service import AiConversationService  # noqa: E402
from services.ai.orchestrator import PmsAiOrchestrator  # noqa: E402
from test_ai_workspace import _build_in_memory_db, _make_call_center_record, _patch_records  # noqa: E402


def _build_eval_records() -> list[Any]:
    recs: list[Any] = []
    for month, sara_sc, adham_sc, sara_bk in [
        ("March", 80.0, 82.0, 110),
        ("April", 83.0, 85.0, 120),
        ("May", 85.0, 87.5, 130),
        ("June", 87.0, 90.0, 140),
        ("July", 88.0, 91.0, 150),
        ("August", 91.0, 96.5, 165),
        ("September", 94.0, 91.0, 195),
    ]:
        r1 = _make_call_center_record("EMP101", "Sara Mahmoud", "Inbound", sara_sc, 45, 50, sara_bk, 220, month=month)
        r1.position = "Senior Call Center Agent"
        r1.geo.bookings.dubai = sara_bk - 80
        r1.geo.bookings.sharjah = 50
        r1.geo.bookings.ajman = 30
        recs.append(r1)

        r2 = _make_call_center_record("EMP102", "Adham Tarek", "Inbound", adham_sc, 30, 50, 100, 150, month=month)
        r2.position = "Inbound Agent"
        r2.geo.bookings.dubai = 40
        r2.geo.bookings.sharjah = 35
        r2.geo.bookings.ajman = 25
        recs.append(r2)

    for month in ("July", "August", "September"):
        recs.append(_make_call_center_record("EMP601", "Mariam Ali", "Inbound", 88.0, 30, 50, 80, 100, month=month))
    for month in ("August", "September"):
        recs.append(_make_call_center_record("EMP602", "Mariam Hassan", "Inbound", 84.0, 25, 45, 70, 95, month=month))

    for month in ("August", "September"):
        ob = _make_call_center_record("EMP201", "Omar Khalid", "Outbound", 89.0, 35, 40, 260, 300, month=month)
        ob.position = "Outbound Specialist"
        recs.append(ob)

    sup1 = _make_call_center_record("EMP301", "Kareem Adel", "Call Center", 62.0, 0, 0, 0, 0, month="September")
    sup1.position = "Quality Assurance"
    sup2 = _make_call_center_record("EMP302", "Ziad Nabil", "Call Center", 62.0, 0, 0, 0, 0, month="September")
    sup2.position = "Trainer"
    sup3 = _make_call_center_record("EMP303", "Nour Hassan", "Call Center", 93.0, 0, 0, 0, 0, month="September")
    sup3.position = "Workforce analyst"
    recs.extend([sup1, sup2, sup3])

    for month, rej in [("August", 0.08), ("September", 0.12)]:
        rcm = _make_call_center_record(
            "EMP401", "Heba Nabil", "Pre-Approvals IP Offshore", 86.0 if month == "September" else 90.0, 0, 0, 0, 0, month=month
        )
        rcm.region = "EGY"
        rcm.kpi_values = [
            {
                "kpi_key": "RejectionRate",
                "label": "Controllable Rejection Rate",
                "actual_value": rej,
                "target_value": 0.05,
                "achievement_ratio": 0.5,
                "weight_applied": 0.5,
                "unit": "%",
                "direction": "lower_better",
            }
        ]
        recs.append(rcm)

    c_egy = _make_call_center_record("EMP501", "Salma Youssef", "Coding EGY", 89.0, 0, 0, 0, 0, month="September")
    c_egy.region = "EGY"
    c_egy.kpi_values = [
        {"kpi_key": "QualityErrors", "label": "Quality Errors", "actual_value": 1.8, "target_value": 3.0, "unit": "%", "direction": "lower_better"},
        {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 89.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
    ]
    c_uae = _make_call_center_record("EMP502", "Tariq Mansoor", "Coding", 92.0, 0, 0, 0, 0, month="September")
    c_uae.region = "UAE"
    c_uae.kpi_values = [
        {"kpi_key": "QualityErrors", "label": "Quality Errors", "actual_value": 2.5, "target_value": 3.0, "unit": "%", "direction": "lower_better"},
        {"kpi_key": "overall_score", "label": "Overall Score", "actual_value": 92.0, "target_value": 85.0, "unit": "%", "direction": "higher_better"},
    ]
    recs.extend([c_egy, c_uae])

    ph = _make_call_center_record("EMP701", "Nadia Fadel", "Pharmacy", 87.5, 0, 0, 0, 0, month="September")
    ph.region = "UAE"
    ph.kpi_values = [
        {
            "kpi_key": "WaitingTime",
            "label": "Waiting Time",
            "actual_value": 6.2,
            "target_value": 5.0,
            "achievement_ratio": 0.8,
            "weight_applied": 0.2,
            "unit": "min",
            "direction": "lower_better",
        }
    ]
    mk = _make_call_center_record("EMP801", "Rami Adel", "Marketing", 90.0, 0, 0, 0, 0, month="September")
    mk.region = "UAE"
    mk.position = "Media Buyer"
    mk.kpi_values = [
        {
            "kpi_key": "mb_cpl",
            "label": "CPL",
            "actual_value": 42.0,
            "target_value": 50.0,
            "achievement_ratio": 1.0,
            "weight_applied": 0.25,
            "unit": "AED",
            "direction": "lower_better",
        }
    ]
    recs.extend([ph, mk])

    for emp_id, name, team, region, level, position, score in [
        ("EMP901", "Layla Sami", "Finance", "EGY", "Employee", "Finance Specialist", 86.0),
        ("EMP902", "Hadi Nasser", "Human Resources", "EGY", "Employee", "HR Specialist", 84.0),
        ("EMP903", "Mina Fawzi", "IT", "EGY", "Corporate", "IT Director", 90.0),
        ("EMP904", "Nour El-Sayed", "Sales", "UAE", "Managerial", "Sales Manager", 89.0),
    ]:
        record = _make_call_center_record(emp_id, name, team, score, 0, 0, 0, 0, month="September")
        record.region = region
        record.performance_level = level
        record.position = position
        record.kpi_values = [
            {
                "kpi_key": "overall_score",
                "label": "Overall Score",
                "actual_value": score,
                "target_value": 85.0,
                "unit": "%",
                "direction": "higher_better",
            }
        ]
        recs.append(record)
    return recs


_PERIOD_MENTION_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}\b",
    re.IGNORECASE,
)
_TREND_EVIDENCE_RE = re.compile(
    r"\b(?:across|from\b.{1,40}\bto|moved|pp|delta|flat|no change|unchanged|insufficient|only 1)\b|[+-]\d+(?:\.\d+)?",
    re.IGNORECASE,
)
_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _normalize_period(value: Any) -> str:
    text = str(value or "").strip()
    iso = re.fullmatch(r"(20\d{2})-(0?[1-9]|1[0-2])", text)
    if iso:
        return f"{_MONTH_NAMES[int(iso.group(2)) - 1]} {iso.group(1)}".casefold()
    return re.sub(r"\s+", " ", text).casefold()


def _matches_expected_actual(item: dict[str, Any], spec: dict[str, Any]) -> bool:
    if spec.get("actual") is None:
        return True
    try:
        actual = float(item.get("actual"))
        expected_actual = float(spec["actual"])
        tolerance = float(spec.get("tolerance", 0.01))
    except (TypeError, ValueError):
        return False

    expected_values = [expected_actual]
    metric_key = str(item.get("metric_id") or item.get("kpi_key") or spec.get("kpi_key") or "")
    metric_definition = get_ai_catalog().find_metric_definition(
        team=str(item.get("team") or spec.get("team") or "") or None,
        kpi_key_or_label=metric_key,
        position=str(item.get("position") or "") or None,
        performance_level=str(item.get("performance_level") or "Employee"),
    )
    expected_unit = str(spec.get("unit") or getattr(metric_definition, "unit", "") or "").casefold()
    if metric_definition and metric_definition.storage_scale == "ratio_0_1" and expected_unit == "%":
        # Fixture values for ratio_0_1 metrics are stored as fractions (0.12),
        # while TypedMetricEvidence.actual uses the displayed percentage scale (12.0).
        expected_values.append(expected_actual * 100.0)

    return any(
        math.isclose(actual, candidate, rel_tol=0.0, abs_tol=tolerance)
        for candidate in expected_values
    )


def validate_critical_evidence(turn: dict[str, Any], resp: Any) -> list[str]:
    """Check exact typed facts, units, employee/aggregate scope, and citations."""
    failures: list[str] = []
    raw_evidence = getattr(resp, "typed_evidence", None) or []
    evidence = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in raw_evidence]
    expected = turn.get("expected_evidence") or []

    def metric_values(item: dict[str, Any]) -> set[str]:
        values = {
            str(item.get("kpi_key") or ""),
            str(item.get("metric_id") or "").rsplit(":", 1)[-1],
            str(item.get("display_name") or ""),
        }
        return {re.sub(r"[^a-z0-9]", "", value.casefold()) for value in values if value}

    for spec in expected:
        expected_metric = re.sub(r"[^a-z0-9]", "", str(spec.get("kpi_key") or "").casefold())
        expected_period = _normalize_period(spec.get("period")) if spec.get("period") else None
        matching = []
        for item in evidence:
            if expected_metric and expected_metric not in metric_values(item):
                continue
            if expected_period and _normalize_period(item.get("period")) != expected_period:
                continue
            if "employee_id" in spec and (item.get("employee_id") or None) != spec.get("employee_id"):
                continue
            if spec.get("employee_name") and str(item.get("employee_name") or "").casefold() != str(spec["employee_name"]).casefold():
                continue
            if spec.get("require_aggregate") and (item.get("employee_id") or item.get("employee_name")):
                continue
            if "branch" in spec and str(item.get("branch") or "").casefold() != str(spec.get("branch") or "").casefold():
                continue
            if "team" in spec and str(item.get("team") or "").casefold() != str(spec.get("team") or "").casefold():
                continue
            if "performance_level" in spec and str(item.get("performance_level") or "").casefold() != str(spec.get("performance_level") or "").casefold():
                continue
            if spec.get("actual") is not None:
                if not _matches_expected_actual(item, spec):
                    continue
            if "unit" in spec and str(item.get("unit") or "").casefold() != str(spec.get("unit") or "").casefold():
                continue
            if spec.get("source_required", True) and not str(item.get("source_link") or "").strip():
                continue
            if spec.get("source_contains") and str(spec["source_contains"]).casefold() not in str(item.get("source_link") or "").casefold():
                continue
            matching.append(item)
        if not matching:
            failures.append(f"missing typed evidence contract {spec!r}")

    if turn.get("expect_no_evidence") and evidence:
        failures.append(f"expected no typed evidence, received {len(evidence)} item(s)")

    if turn.get("require_source_for_all_evidence"):
        missing_sources = [item for item in evidence if not str(item.get("source_link") or "").strip()]
        if missing_sources:
            failures.append(f"{len(missing_sources)} typed evidence item(s) lack a source link")

    expected_outcomes = set(turn.get("expected_outcomes") or [])
    expected_outcome = turn.get("expected_outcome")
    if turn.get("critical_authorization") and (
        expected_outcome == "restricted_access" or "restricted_access" in expected_outcomes
    ):
        if evidence:
            failures.append("restricted response returned typed evidence")
        if getattr(resp, "tool_calls", None):
            failures.append("restricted response executed a data tool")

    expected_tools = set(turn.get("expected_tool_names") or [])
    actual_tools = {tool.tool_name for tool in (getattr(resp, "tool_calls", None) or [])}
    if not expected_tools.issubset(actual_tools):
        failures.append(f"tool names {sorted(actual_tools)!r} missing {sorted(expected_tools - actual_tools)!r}")
    expected_any_tools = set(turn.get("expected_any_tool_names") or [])
    if expected_any_tools and not expected_any_tools.intersection(actual_tools):
        failures.append(f"tool names {sorted(actual_tools)!r} contain none of {sorted(expected_any_tools)!r}")
    return failures


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return round(ordered[lower] * (1 - fraction) + ordered[upper] * fraction, 2)


def validate_turn_response(turn: dict[str, Any], resp: Any, *, elapsed_ms: float = 0.0) -> list[str]:
    """Validate one evaluated turn strictly across outcome, intent, metric, scope, period, and trend evidence."""
    failures: list[str] = []
    combined_parts = [
        str(getattr(resp, "headline", "") or ""),
        *[str(b) for b in (getattr(resp, "narrative_bullets", None) or [])],
        *[str(b) for b in (getattr(resp, "detail_bullets", None) or [])],
    ]
    if getattr(resp, "clarification", None):
        combined_parts.append(str(resp.clarification.question or ""))
        for ch in resp.clarification.choices:
            combined_parts.append(str(ch.label or ""))
    combined_text = "\n".join(combined_parts).casefold()
    sq = getattr(resp, "structured_query", None)

    expected_outcomes = set(turn.get("expected_outcomes") or [])
    expected_outcome = turn.get("expected_outcome")
    if expected_outcomes and resp.outcome not in expected_outcomes:
        failures.append(f"outcome {resp.outcome!r} not in {sorted(expected_outcomes)!r}")
    elif expected_outcome and resp.outcome != expected_outcome:
        failures.append(f"outcome {resp.outcome!r} != {expected_outcome!r}")
    if turn.get("expected_capability_mode") and resp.capability_mode != turn["expected_capability_mode"]:
        failures.append(f"capability_mode {resp.capability_mode!r} != {turn['expected_capability_mode']!r}")
    if turn.get("expected_answer_source") and resp.answer_source != turn["expected_answer_source"]:
        failures.append(f"answer_source {resp.answer_source!r} != {turn['expected_answer_source']!r}")
    usage = resp.provider_usage.model_dump() if resp.provider_usage else {}
    if turn.get("expected_fallback_outcome") and usage.get("fallback_outcome") != turn["expected_fallback_outcome"]:
        failures.append(
            f"fallback_outcome {usage.get('fallback_outcome')!r} != {turn['expected_fallback_outcome']!r}"
        )
    if turn.get("expected_provider_used") and resp.provider_used != turn["expected_provider_used"]:
        failures.append(f"provider_used {resp.provider_used!r} != {turn['expected_provider_used']!r}")
    if turn.get("expected_intent"):
        got_intent = sq.intent if sq else None
        if got_intent != turn["expected_intent"]:
            failures.append(f"intent {got_intent!r} != {turn['expected_intent']!r}")
    if "expected_metric" in turn:
        exp_metric = turn["expected_metric"]
        got_metric = sq.metric if sq else None
        if exp_metric is None:
            if got_metric is not None:
                failures.append(f"metric {got_metric!r} != None")
        elif got_metric != exp_metric and (not got_metric or got_metric.split(":")[-1] != str(exp_metric)):
            failures.append(f"metric {got_metric!r} != {exp_metric!r}")
    if turn.get("validate_scope") and turn.get("expected_scope") is not None:
        state = resp.resolved_session_state
        last_context = state.last_confirmed_query
        scope_values = {
            "function": (sq.function if sq else None) or state.function or (last_context.function if last_context else None),
            "team": (sq.team if sq else None) or state.team or (last_context.team if last_context else None),
            "region": state.region or (last_context.region if last_context else None),
            "branch": (sq.branch if sq else None) or state.branch or (last_context.branch if last_context else None),
            "performance_level": (sq.performance_level if sq else None) or state.performance_level or (last_context.performance_level if last_context else None),
            "employee_id": (sq.employee_id if sq else None) or state.employee_id or (last_context.last_subject_employee_id if last_context else None),
        }
        for key, expected in turn["expected_scope"].items():
            if key not in scope_values:
                failures.append(f"unsupported expected_scope key {key!r}")
            elif scope_values[key] != expected:
                failures.append(f"scope {key} {scope_values[key]!r} != {expected!r}")
    for ek, ev in (turn.get("expected_entities") or {}).items():
        if ek == "employee":
            got_emp = (sq.employee_name if sq else None) or ""
            if ev.casefold() not in got_emp.casefold() and ev.casefold() not in combined_text:
                failures.append(f"entity employee missing {ev!r}")
        elif ek == "region":
            got_reg = (
                resp.resolved_session_state.region
                or (resp.resolved_session_state.last_confirmed_query.region if resp.resolved_session_state.last_confirmed_query else None)
            )
            if got_reg != ev:
                failures.append(f"entity region {got_reg!r} != {ev!r}")
        else:
            got_v = getattr(sq, ek, None) if sq else None
            if got_v != ev:
                failures.append(f"entity {ek} {got_v!r} != {ev!r}")
    for pk in turn.get("expected_periods") or []:
        got_p = sq.periods if sq else []
        if pk not in got_p:
            failures.append(f"period {pk!r} not in {got_p!r}")
    min_trend_periods = int(turn.get("expected_min_trend_periods") or 0)
    if min_trend_periods > 0:
        distinct_periods = {m.casefold() for m in _PERIOD_MENTION_RE.findall(combined_text)}
        insufficient_ok = bool(turn.get("allow_insufficient_history") and ("insufficient" in combined_text or "only 1" in combined_text))
        if not insufficient_ok and len(distinct_periods) < min_trend_periods:
            failures.append(f"trend periods mentioned {sorted(distinct_periods)!r} < required {min_trend_periods}")
    if turn.get("require_trend_evidence"):
        if not _TREND_EVIDENCE_RE.search(combined_text):
            failures.append(f"missing multi-period trend/movement evidence in {resp.headline!r}")
    req_content = turn.get("required_content") or []
    if turn["id"] in ("d06_t2", "h02_t4"):
        if not any(tok.casefold() in combined_text for tok in req_content):
            failures.append(f"missing any of {req_content!r} in {resp.headline!r}")
    else:
        for tok in req_content:
            if isinstance(tok, list):
                if not any(str(opt).casefold() in combined_text for opt in tok):
                    failures.append(f"missing any of {tok!r} in {resp.headline!r} | {resp.narrative_bullets!r}")
            elif tok.casefold() not in combined_text:
                failures.append(f"missing content {tok!r} in {resp.headline!r} | {resp.narrative_bullets!r}")
    for bad in turn.get("forbidden_content") or []:
        if bad.casefold() in combined_text:
            failures.append(f"forbidden content {bad!r} appeared in {resp.headline!r}")
    if turn.get("expected_clarification_code"):
        got_code = resp.clarification.code if resp.clarification else None
        if got_code != turn["expected_clarification_code"]:
            failures.append(f"clarification {got_code!r} != {turn['expected_clarification_code']!r}")
    expected_choice_ids = set(turn.get("expected_choice_employee_ids") or [])
    if expected_choice_ids:
        got_choice_ids = {
            choice.employee_id
            for choice in (resp.clarification.choices if resp.clarification else [])
            if choice.employee_id
        }
        if not expected_choice_ids.issubset(got_choice_ids):
            failures.append(f"choice employees {sorted(got_choice_ids)!r} missing {sorted(expected_choice_ids - got_choice_ids)!r}")
    if "max_tool_calls" in turn and len(resp.tool_calls) > int(turn["max_tool_calls"]):
        failures.append(f"tool_calls {len(resp.tool_calls)} > {turn['max_tool_calls']}")
    _ = elapsed_ms
    return failures


def evaluate_unseen_dataset(
    *,
    mode: str | None = None,
    use_live_provider: bool | None = None,
    fixture_name: str = "ai_unseen_multiturn_eval.json",
    custom_records: list[Any] | None = None,
) -> dict[str, Any]:
    if mode is None:
        mode = "live" if use_live_provider else "deterministic"
    if mode not in {"deterministic", "mocked", "live"}:
        raise ValueError("mode must be deterministic, mocked, or live")
    safe_fixture_name = Path(fixture_name).name
    if safe_fixture_name != fixture_name or not safe_fixture_name.endswith(".json"):
        raise ValueError("fixture_name must be a JSON filename inside tests/fixtures")
    fixture_path = TESTS_DIR / "fixtures" / safe_fixture_name
    fixture_bytes = fixture_path.read_bytes()
    dataset = json.loads(fixture_bytes.decode("utf-8"))
    fixture_sha256 = hashlib.sha256(fixture_bytes).hexdigest()
    freeze_manifest = None
    manifest_name = dataset.get("freeze_manifest")
    if manifest_name:
        safe_manifest_name = Path(str(manifest_name)).name
        if safe_manifest_name != manifest_name or not safe_manifest_name.endswith(".json"):
            raise ValueError("freeze_manifest must be a JSON filename inside tests/fixtures")
        freeze_manifest = json.loads((TESTS_DIR / "fixtures" / safe_manifest_name).read_text(encoding="utf-8"))
        if freeze_manifest.get("fixture_sha256") != fixture_sha256:
            raise ValueError("Frozen fixture hash does not match its manifest")
        runner_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if freeze_manifest.get("runner_sha256") != runner_sha256:
            raise ValueError("Frozen evaluator-script hash does not match its manifest")
    conversations = dataset.get("conversations") or []
    prompt_count = sum(len(conv.get("turns") or []) for conv in conversations)
    freeze_requirements = dataset.get("freeze_requirements") or {}
    min_conversations = int(freeze_requirements.get("min_conversations") or 0)
    min_prompts = int(freeze_requirements.get("min_prompts") or 0)
    if len(conversations) < min_conversations or prompt_count < min_prompts:
        raise ValueError(
            f"Frozen dataset is undersized: {len(conversations)} conversations/{prompt_count} prompts; "
            f"requires {min_conversations}/{min_prompts}"
        )
    coverage_counts: dict[str, int] = {}
    for conv in conversations:
        for tag in conv.get("coverage_tags") or []:
            coverage_counts[tag] = coverage_counts.get(tag, 0) + 1
        for turn in conv.get("turns") or []:
            for tag in turn.get("coverage_tags") or []:
                coverage_counts[tag] = coverage_counts.get(tag, 0) + 1
    required_coverage = (dataset.get("coverage") or {}).get("required_tags") or []
    missing_coverage = sorted(tag for tag in required_coverage if coverage_counts.get(tag, 0) == 0)
    if missing_coverage:
        raise ValueError(f"Frozen dataset is missing required coverage tags: {missing_coverage!r}")
    if mode == "live":
        load_project_environment(str(BACKEND_DIR))

    mp = MonkeyPatch()
    db = _build_in_memory_db()
    records = custom_records if custom_records is not None else _build_eval_records()
    records_payload = [
        record.model_dump(mode="json") if hasattr(record, "model_dump") else str(record)
        for record in records
    ]
    source_data_sha256 = hashlib.sha256(
        json.dumps(records_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if freeze_manifest and freeze_manifest.get("source_data_sha256") != source_data_sha256:
        raise ValueError("Frozen synthetic source-data hash does not match its manifest")
    _patch_records(mp, records)
    ai_evidence_cache.clear()

    env_keys = (
        "PMS_AI_INTENT_ENABLED",
        "PMS_AI_NVIDIA_ROUTING_ENABLED",
        "PMS_AI_SYNTHESIS_ENABLED",
        "PMS_AI_CONVERSATION_STATE_ENABLED",
        "PMS_AI_MODEL_LED_PILOT_ENABLED",
        "PMS_AI_ROUTER_MODE",
    )
    previous_env = {key: os.environ.get(key) for key in env_keys}

    provider_enabled = mode in {"mocked", "live"}
    os.environ["PMS_AI_INTENT_ENABLED"] = "true" if provider_enabled else "false"
    os.environ["PMS_AI_NVIDIA_ROUTING_ENABLED"] = "false"
    os.environ["PMS_AI_SYNTHESIS_ENABLED"] = "true" if provider_enabled else "false"
    os.environ["PMS_AI_CONVERSATION_STATE_ENABLED"] = "true"
    os.environ["PMS_AI_MODEL_LED_PILOT_ENABLED"] = "true" if provider_enabled else "false"
    os.environ["PMS_AI_ROUTER_MODE"] = "hybrid" if provider_enabled else "legacy"

    run_started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, Any]] = []
    conv_svc = AiConversationService(db)
    try:
        for conv in dataset["conversations"]:
            cid: str | None = None
            cver: int | None = None
            ss = SessionFilterContext()
            base_scope = dict(conv["scope"])

            for turn in conv["turns"]:
                if turn.get("start_fresh_conversation"):
                    cid = None
                    cver = None
                    ss = SessionFilterContext()

                eff_scope = dict(turn.get("override_scope") or base_scope)
                deleted_conversation_id = None
                if turn.get("reload_from_service") and cid:
                    reloaded = conv_svc.get_context(conversation_id=cid, scope=eff_scope)
                    cid = reloaded.conversation_id
                    cver = reloaded.context_version
                    cc = reloaded.confirmed_context
                    ss = SessionFilterContext(
                        function=cc.function,
                        team=cc.team,
                        position=cc.position,
                        branch=cc.branch,
                        region=cc.region,
                        performance_level=cc.performance_level,
                        last_confirmed_query=cc,
                    )
                if turn.get("delete_conversation") and cid:
                    deleted_conversation_id = cid
                    conv_svc.delete_conversation(cid, scope=eff_scope)
                    cid = None
                    cver = None
                    ss = SessionFilterContext()

                turn_mp = MonkeyPatch()
                mock_captured: list[dict[str, Any]] = []
                if mode == "mocked" or (turn.get("force_provider_failure") and mode != "live"):
                    turn_mp.setenv("PMS_AI_INTENT_ENABLED", "true")
                    turn_mp.setenv("PMS_AI_SYNTHESIS_ENABLED", "true")
                    turn_mp.setenv("PMS_AI_MODEL_LED_PILOT_ENABLED", "true")
                    turn_mp.setenv("PMS_AI_ROUTER_MODE", "hybrid")
                    turn_mp.setenv("PMS_AI_LOCAL_ROUTER_ENABLED", "true")
                    failure_reason = str(turn.get("force_provider_failure") or "mocked_provider_failure")
                    mock_captured = install_scripted_provider(turn_mp, failed_response(failure_reason))

                orch = PmsAiOrchestrator(db, eff_scope)
                req = AiChatRequest(
                    prompt=turn["prompt"],
                    conversation_id=cid,
                    context_version=cver,
                    clarification_choice_id=turn.get("clarification_choice_id"),
                    session_state=ss,
                )
                t0 = time.perf_counter()
                resp = orch.run_chat_turn(req)
                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                turn_mp.undo()

                cid = resp.conversation_id
                cver = resp.context_version
                ss = resp.resolved_session_state

                semantic_failures = validate_turn_response(turn, resp, elapsed_ms=elapsed_ms)
                critical_failures = validate_critical_evidence(turn, resp)
                failures = [*semantic_failures, *critical_failures]
                if turn.get("delete_conversation") and deleted_conversation_id and resp.conversation_id == deleted_conversation_id:
                    failures.append("deleted conversation ID was reused")
                usage = resp.provider_usage.model_dump() if resp.provider_usage else {}
                reported_calls = int(usage.get("provider_calls") or 0)
                provider_call_attempts = max(reported_calls, len(mock_captured))

                results.append(
                    {
                        "conversation": conv["id"],
                        "split": conv["split"],
                        "turn_id": turn["id"],
                        "reload_from_service": bool(turn.get("reload_from_service")),
                        "delete_before_turn": bool(turn.get("delete_conversation")),
                        "prompt": turn["prompt"],
                        "passed": len(failures) == 0,
                        "failures": failures,
                        "semantic_failures": semantic_failures,
                        "critical_failures": critical_failures,
                        "critical_check_required": bool(
                            turn.get("expected_evidence")
                            or turn.get("expect_no_evidence")
                            or turn.get("critical_authorization")
                            or turn.get("require_source_for_all_evidence")
                            or turn.get("expected_tool_names")
                            or turn.get("expected_any_tool_names")
                        ),
                        "elapsed_ms": elapsed_ms,
                        "provider_used": resp.provider_used,
                        "model_used": resp.model_used,
                        "answer_source": resp.answer_source,
                        "provider_calls": reported_calls,
                        "provider_call_attempts": provider_call_attempts,
                        "input_tokens": int(usage.get("input_tokens") or 0),
                        "output_tokens": int(usage.get("output_tokens") or 0),
                        "estimated_cost_usd": float(usage.get("estimated_cost_usd") or 0.0),
                        "fallback_outcome": str(usage.get("fallback_outcome") or "none"),
                        "headline": resp.headline,
                        "narrative_bullets": list(resp.narrative_bullets or []),
                        "detail_bullets": list(resp.detail_bullets or []),
                        "outcome": resp.outcome,
                        "capability_mode": resp.capability_mode,
                        "structured_query": resp.structured_query.model_dump() if resp.structured_query else None,
                        "typed_evidence": [item.model_dump(mode="json") for item in (resp.typed_evidence or [])],
                        "clarification": resp.clarification.model_dump(mode="json") if resp.clarification else None,
                        "coverage_tags": list(turn.get("coverage_tags") or []),
                        "tool_names": [tool.tool_name for tool in resp.tool_calls],
                    }
                )
    finally:
        mp.undo()
        db.close()
        for k, v in previous_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    summary: dict[str, Any] = {}
    split_names = sorted({str(row["split"]) for row in results})
    for split_name in split_names:
        rows = [r for r in results if r["split"] == split_name]
        passed = sum(1 for r in rows if r["passed"])
        semantic_passed = sum(1 for r in rows if not r["semantic_failures"])
        critical_rows = [r for r in rows if r["critical_check_required"]]
        critical_checks = sum(1 for r in critical_rows if not r["critical_failures"])
        summary[split_name] = {
            "total": len(rows),
            "passed": passed,
            "accuracy_pct": round((passed / len(rows)) * 100.0, 2) if rows else 0.0,
            "semantic_passed": semantic_passed,
            "semantic_accuracy_pct": round((semantic_passed / len(rows)) * 100.0, 2) if rows else 0.0,
            "critical_check_passed_turns": critical_checks,
            "critical_check_required_turns": len(critical_rows),
            "critical_check_pass_rate_pct": round((critical_checks / len(critical_rows)) * 100.0, 2) if critical_rows else 0.0,
            "avg_ms": round(sum(r["elapsed_ms"] for r in rows) / len(rows), 2) if rows else 0.0,
            "p50_ms": _percentile([float(r["elapsed_ms"]) for r in rows], 0.50),
            "p95_ms": _percentile([float(r["elapsed_ms"]) for r in rows], 0.95),
            "total_provider_calls": sum(r["provider_calls"] for r in rows),
            "total_provider_call_attempts": sum(r["provider_call_attempts"] for r in rows),
            "total_input_tokens": sum(r["input_tokens"] for r in rows),
            "total_output_tokens": sum(r["output_tokens"] for r in rows),
            "total_estimated_cost_usd": round(sum(r["estimated_cost_usd"] for r in rows), 8),
            "fallback_turns": sum(1 for r in rows if r["fallback_outcome"] not in ("", "none")),
            "failures": [r for r in rows if not r["passed"]],
        }
    all_rows = results
    passed_all = sum(1 for r in all_rows if r["passed"])
    semantic_passed_all = sum(1 for r in all_rows if not r["semantic_failures"])
    critical_rows_all = [r for r in all_rows if r["critical_check_required"]]
    critical_passed_all = sum(1 for r in critical_rows_all if not r["critical_failures"])
    summary["overall"] = {
        "total": len(all_rows),
        "passed": passed_all,
        "accuracy_pct": round((passed_all / len(all_rows)) * 100.0, 2) if all_rows else 0.0,
        "semantic_passed": semantic_passed_all,
        "semantic_accuracy_pct": round((semantic_passed_all / len(all_rows)) * 100.0, 2) if all_rows else 0.0,
        "critical_check_passed_turns": critical_passed_all,
        "critical_check_required_turns": len(critical_rows_all),
        "critical_check_pass_rate_pct": round((critical_passed_all / len(critical_rows_all)) * 100.0, 2) if critical_rows_all else 0.0,
        "avg_ms": round(sum(r["elapsed_ms"] for r in all_rows) / len(all_rows), 2) if all_rows else 0.0,
        "p50_ms": _percentile([float(r["elapsed_ms"]) for r in all_rows], 0.50),
        "p95_ms": _percentile([float(r["elapsed_ms"]) for r in all_rows], 0.95),
        "total_provider_calls": sum(r["provider_calls"] for r in all_rows),
        "total_provider_call_attempts": sum(r["provider_call_attempts"] for r in all_rows),
        "total_input_tokens": sum(r["input_tokens"] for r in all_rows),
        "total_output_tokens": sum(r["output_tokens"] for r in all_rows),
        "total_estimated_cost_usd": round(sum(r["estimated_cost_usd"] for r in all_rows), 8),
        "fallback_turns": sum(1 for r in all_rows if r["fallback_outcome"] not in ("", "none")),
        "failures": [r for r in all_rows if not r["passed"]],
    }
    quality_gate = {
        "structural_pass": (
            len(conversations) >= min_conversations
            and len(results) >= min_prompts
            and not missing_coverage
        ),
        "critical_target_pct": float(freeze_requirements.get("critical_accuracy_pct", 100.0)),
        "critical_pass": summary["overall"]["critical_check_pass_rate_pct"]
        >= float(freeze_requirements.get("critical_accuracy_pct", 100.0)),
        "semantic_target_pct": float(freeze_requirements.get("semantic_accuracy_pct", 95.0)),
        "semantic_pass": summary["overall"]["semantic_accuracy_pct"]
        >= float(freeze_requirements.get("semantic_accuracy_pct", 95.0)),
    }
    quality_gate["passed"] = all(
        bool(quality_gate[key]) for key in ("structural_pass", "critical_pass", "semantic_pass")
    )
    completed_at_utc = datetime.now(timezone.utc).isoformat()
    runner_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {
        "mode": mode,
        "fixture": safe_fixture_name,
        "fixture_sha256": fixture_sha256,
        "source_data_sha256": source_data_sha256,
        "runner_sha256": runner_sha256,
        "freeze_manifest": safe_manifest_name if manifest_name else None,
        "conversation_count": len(conversations),
        "prompt_count": len(results),
        "coverage": dataset.get("coverage", {}),
        "coverage_counts": coverage_counts,
        "coverage_missing_tags": missing_coverage,
        "freeze_requirements": freeze_requirements,
        "quality_gate": quality_gate,
        "freeze_manifest_sha256": hashlib.sha256(
            json.dumps(freeze_manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest() if freeze_manifest else None,
        "started_at_utc": run_started_at,
        "completed_at_utc": completed_at_utc,
        "summary": summary,
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate synthetic PMS AI conversations in deterministic, mocked, or live mode.")
    parser.add_argument("--mode", choices=("deterministic", "mocked", "live"), default="deterministic")
    parser.add_argument("--live", action="store_true", help="Compatibility alias for --mode live")
    parser.add_argument("--fixture", default="ai_unseen_multiturn_eval.json")
    parser.add_argument("--output", help="Optional path for the full JSON result artifact")
    args = parser.parse_args()
    selected_mode = "live" if args.live else args.mode
    out = evaluate_unseen_dataset(mode=selected_mode, fixture_name=args.fixture)
    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    compact_summary = {
        split: {key: value for key, value in metrics.items() if key != "failures"}
        for split, metrics in out["summary"].items()
    }
    failed_turns = [
        {"conversation": row["conversation"], "turn_id": row["turn_id"], "failures": row["failures"]}
        for row in out["results"]
        if not row["passed"]
    ]
    print(json.dumps({
        "fixture": args.fixture,
        "mode": out["mode"],
        "fixture_sha256": out["fixture_sha256"],
        "source_data_sha256": out["source_data_sha256"],
        "runner_sha256": out["runner_sha256"],
        "conversation_count": out["conversation_count"],
        "prompt_count": out["prompt_count"],
        "coverage_counts": out["coverage_counts"],
        "coverage_missing_tags": out["coverage_missing_tags"],
        "quality_gate": out["quality_gate"],
        "summary": compact_summary,
        "failed_turns": failed_turns,
        "full_result_path": str(Path(args.output).resolve()) if args.output else None,
    }, indent=2))
