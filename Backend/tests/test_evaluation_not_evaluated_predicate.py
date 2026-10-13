"""Predicate for not-evaluated employee-months (pure, synthetic values only)."""
from __future__ import annotations

import math

import pytest

from services.evaluation.not_evaluated import (
    actuals_by_key,
    is_missing_actual,
    missing_weighted_keys,
    normalise_actual_cells,
    not_evaluated_reason,
    reason_text,
    status_evidence,
    status_label,
    weighted_keys,
)

LINES = [
    {"kpi_key": "QualityErrors", "weight": 0.5},
    {"kpi_key": "Rejection", "weight": 0.3},
    {"kpi_key": "TAT", "weight": 0.2},
]


@pytest.mark.parametrize(
    ("status", "label"),
    [
        ("Leave", "on leave"),
        ("On leave", "on leave"),
        ("LEAVE", "on leave"),
        ("  leave  ", "on leave"),
        ("Inactive", "inactive"),
        ("inactive ", "inactive"),
        ("Active - New", "new"),
        ("New", "new"),
        ("new", "new"),
        ("New Starter", "new"),
    ],
)
def test_status_spellings_that_mark_not_evaluated(status, label):
    assert status_label(status) == label


@pytest.mark.parametrize("status", ["Active", "Renewed", "Renewal due", "", "   ", None, "Meets", "Below"])
def test_evaluated_or_empty_statuses_do_not_mark_a_row(status):
    assert status_label(status) is None


def test_status_evidence_prefers_the_status_text_over_flags():
    assert status_evidence({"Status": "Active", "Is_New": True}) is None
    assert status_evidence({"Status": "Active - New", "Is_New": False}) == "new"


def test_status_evidence_falls_back_to_the_cleaner_flags_only_without_status_text():
    assert status_evidence({"Is_Inactive": True}) == "inactive"
    assert status_evidence({"Is_New": "True"}) == "new"
    assert status_evidence({"Is_New": False, "Is_Inactive": False}) is None
    assert status_evidence({"Status": None, "Is_New": True}) == "new"


def test_status_evidence_ignores_the_performance_status_column():
    # The record's own status (Exceeds, Meets, Below) is not workbook status.
    assert status_evidence({"status": "Meets"}) is None
    assert status_evidence(None) is None
    assert status_evidence({}) is None


def test_a_zero_weight_kpi_does_not_count_as_weighted():
    lines = [{"kpi_key": "QualityErrors", "weight": 0}, {"kpi_key": "Rejection", "weight": 0.5}]
    assert weighted_keys(lines) == ["Rejection"]


@pytest.mark.parametrize(
    ("status", "label"),
    [("Leave", "on leave"), ("Inactive", "inactive"), ("Active - New", "new")],
)
def test_no_actual_for_any_weighted_kpi_is_not_evaluated(status, label):
    actuals = {"QualityErrors": None, "Rejection": None, "TAT": None}
    assert not_evaluated_reason(LINES, actuals, {"Status": status}) == label


def test_a_blank_string_or_nan_actual_counts_as_no_actual():
    actuals = {"QualityErrors": "  ", "Rejection": math.nan, "TAT": None}
    assert not_evaluated_reason(LINES, actuals, {"Status": "Leave"}) == "on leave"


def test_a_status_row_with_some_weighted_actuals_missing_is_not_evaluated():
    # The real new-employee shape: a number, a dash, a number. Partial status rows do not block.
    actuals = {"QualityErrors": 0.0, "Rejection": "-", "TAT": 0.8}
    assert not_evaluated_reason(LINES, actuals, {"Status": "Active - New"}) == "new"


@pytest.mark.parametrize("status", ["Active", "Meets", ""])
def test_an_evaluated_status_with_a_missing_weighted_actual_stays_strict(status):
    actuals = {"QualityErrors": 60.0, "Rejection": None, "TAT": 55.0}
    assert not_evaluated_reason(LINES, actuals, {"Status": status}) is None


def test_all_weighted_actuals_are_scored_normally():
    actuals = {"QualityErrors": 60.0, "Rejection": 55.0, "TAT": 55.0}
    assert not_evaluated_reason(LINES, actuals, {"Status": "Leave"}) is None


def test_an_actual_on_an_unweighted_kpi_does_not_make_the_row_evaluated():
    lines = [{"kpi_key": "QualityErrors", "weight": 0.5}, {"kpi_key": "Other", "weight": 0}]
    assert not_evaluated_reason(lines, {"QualityErrors": None, "Other": 5.0}, {"Status": "Leave"}) == "on leave"


def test_an_evaluated_status_with_no_actuals_stays_strict():
    actuals = {"QualityErrors": None, "Rejection": None, "TAT": None}
    assert not_evaluated_reason(LINES, actuals, {"Status": "Active"}) is None


def test_no_status_evidence_with_no_actuals_stays_strict():
    actuals = {"QualityErrors": None, "Rejection": None, "TAT": None}
    assert not_evaluated_reason(LINES, actuals, {}) is None
    assert not_evaluated_reason(LINES, actuals, None) is None


def test_reason_text_is_the_reported_wording():
    assert reason_text("on leave") == "Not evaluated: on leave, no actuals"


def test_actuals_by_key_reads_scoring_rows_and_evidence_rows():
    assert actuals_by_key([{"kpi_key": "A", "actual": 1.0}]) == {"A": 1.0}
    assert actuals_by_key([{"kpi_key": "A", "actual_value": None}]) == {"A": None}


@pytest.mark.parametrize("marker", ["-", " - ", "–", "—", "N/A", "NA", "n/a", "na", "", "   ", None, math.nan])
def test_missing_markers_count_as_no_actual(marker):
    assert is_missing_actual(marker) is True


@pytest.mark.parametrize("value", [0, 0.0, 55, "55", "0", "12abc", "[1]", True, False])
def test_numbers_and_malformed_values_are_not_missing_markers(value):
    # Malformed text is left to the number parser, which still raises invalid_evidence.
    assert is_missing_actual(value) is False


def test_status_row_with_a_marker_in_a_weighted_actual_is_not_evaluated_and_partial_is_named():
    assert not_evaluated_reason(LINES, {"QualityErrors": 0.0, "Rejection": "-", "TAT": 0.8}, {"Status": "New"}) == "new"
    assert missing_weighted_keys(LINES, {"QualityErrors": 0.0, "Rejection": "-", "TAT": 0.8}) == ["Rejection"]
    assert reason_text("new", ["Rejection"], ["QualityErrors", "Rejection", "TAT"]) == "Not evaluated: new, actual missing for Rejection"
    assert reason_text("new", ["QualityErrors", "Rejection", "TAT"], ["QualityErrors", "Rejection", "TAT"]) == "Not evaluated: new, no actuals"


def test_normalise_actual_cells_blanks_only_the_configured_actual_cells():
    config = {"kpis": [{"key": "Rejection", "actual_col": "A.RejectionRate", "target_col": "T.RejectionRate"}]}
    raw = {"A.RejectionRate": "-", "T.RejectionRate": "-", "Status": "New", "A.Other": "-"}
    normalised = normalise_actual_cells(config, raw)
    assert normalised["A.RejectionRate"] is None
    assert normalised["T.RejectionRate"] == "-"  # targets are not normalised here
    assert normalised["A.Other"] == "-"
    assert raw["A.RejectionRate"] == "-"  # the original row is not changed


def test_normalise_actual_cells_matches_a_header_by_its_folded_name():
    config = {"kpis": [{"key": "TAT", "actual_col": "A.TAT"}]}
    assert normalise_actual_cells(config, {"a. tat": float("nan")})["a. tat"] is None
    assert normalise_actual_cells(None, {"A.TAT": "-"}) == {"A.TAT": "-"}
