from __future__ import annotations

from scripts.rescore_phase5_frozen_outputs_v1 import (
    _summary,
    _count_unit_alias_is_valid,
    rescore_semantic_metadata,
)


def test_postfix_rescore_uses_canonical_ranking_metadata_without_changing_outcome() -> None:
    turn = {"id": "p502_t1", "expected_intent": "ranking"}
    row = {
        "semantic_failures": ["intent 'current_value' != 'ranking'"],
        "structured_query": {
            "intent": "current_value",
            "requested_parts": ["ranking"],
            "operation_kind_v2": "ranking",
        },
        "typed_evidence": [],
    }

    failures, normalizations = rescore_semantic_metadata(turn, row)

    assert failures == []
    assert normalizations == ["legacy intent resolved through canonical operation metadata 'ranking'"]
    assert row["structured_query"]["intent"] == "current_value"


def test_postfix_rescore_does_not_accept_metric_alias_without_matching_typed_evidence() -> None:
    turn = {"id": "p507_t1", "expected_metric": "waitingtime"}
    row = {
        "semantic_failures": ["metric None != 'waitingtime'"],
        "structured_query": {
            "metric": None,
            "model_led_tool_call": {
                "tool_name": "read_employee_metric",
                "tool_arguments": {"metric_id": "waitingtime"},
            },
        },
        "typed_evidence": [],
    }

    failures, normalizations = rescore_semantic_metadata(turn, row)

    assert failures == ["metric None != 'waitingtime'"]
    assert normalizations == []


def test_postfix_rescore_allows_catalog_count_alias_without_mutating_evidence() -> None:
    item = {
        "metric_id": "outbound:bookings_count",
        "kpi_key": "bookings_count",
        "team": "Outbound",
        "performance_level": "Employee",
        "unit": "bookings",
    }
    spec = {"kpi_key": "bookings_count", "team": "Outbound", "unit": "count"}

    assert _count_unit_alias_is_valid(item, spec)
    assert item["unit"] == "bookings"


def test_postfix_rescore_does_not_equate_count_with_percentage() -> None:
    item = {
        "metric_id": "inbound:booking_rate",
        "kpi_key": "booking_rate",
        "team": "Inbound",
        "performance_level": "Employee",
        "unit": "%",
    }
    spec = {"kpi_key": "booking_rate", "team": "Inbound", "unit": "count"}

    assert not _count_unit_alias_is_valid(item, spec)


def test_country_specific_query_metric_requires_its_own_source_fact() -> None:
    query_metric = "coding_egy:rcm_shj_op_coding:quality_errors_rate"
    turn = {"expected_metric": "QualityErrors"}
    failure = f"metric '{query_metric}' != 'QualityErrors'"
    fact = {
        "metric_id": query_metric, "kpi_key": "QualityErrors", "source_link": "/team/coding-egy",
    }
    row = {
        "structured_query": {"metric": query_metric}, "semantic_failures": [failure],
        "typed_evidence": [fact],
    }
    assert rescore_semantic_metadata(turn, row)[0] == []
    fact["metric_id"] = "coding:quality_errors"
    assert rescore_semantic_metadata(turn, row)[0] == [failure]


def test_postfix_rescore_summary_uses_rescored_row_fields() -> None:
    summary = _summary(
        [
            {
                "rescored_semantic_failures": [],
                "rescored_critical_failures": [],
                "critical_check_required": True,
                "rescored_passed": True,
            },
            {
                "rescored_semantic_failures": ["semantic"],
                "rescored_critical_failures": ["critical"],
                "critical_check_required": True,
                "rescored_passed": False,
            },
        ],
        thresholds={"semantic_accuracy_pct": 95, "critical_accuracy_pct": 100},
        original={},
    )

    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["semantic_accuracy_pct"] == 50.0
    assert summary["critical_check_pass_rate_pct"] == 50.0
    assert summary["quality_gate"]["passed"] is False
