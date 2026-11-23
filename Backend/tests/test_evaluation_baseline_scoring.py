"""Characterize current scoring. These assertions record today's functions.

They are not a statement that read-time reinterpretation, precomputed bypass,
or repository targets are the desired monthly-settings policy.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from config.loader import load_team_config, resolve_team_config
from services.kpi_service import DEFAULT_TARGETS, KPIService
from services.scoring.engine import EMPLOYEE_POLICY, achievement


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "evaluation_baseline"


class _EmptyRepo:
    def get_by_team(self, _team):
        return None


def _service() -> KPIService:
    return KPIService(_EmptyRepo(), _EmptyRepo())


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _csr_row(target: float, month_label: str) -> dict:
    fixture = _load("csr_queries_rows.json")
    row = dict(fixture["neutral_columns"])
    row[fixture["actual_column"]] = fixture["actual"]
    row[fixture["target_column"]] = target
    row["Month"] = month_label
    return row


def test_employee_policy_caps_july_and_scores_august_from_synthetic_ratios():
    fixture = _load("july_august_attendance.json")
    actual = fixture["actual"]
    july = achievement(actual, fixture["july_target"], "higher_better", EMPLOYEE_POLICY)
    august = achievement(actual, fixture["august_target"], "higher_better", EMPLOYEE_POLICY)

    assert july.value == 1.0
    assert july.raw_ratio == pytest.approx(0.6 / 0.55)
    assert august.value == pytest.approx(0.6 / 0.65)
    assert august.raw_ratio == pytest.approx(0.6 / 0.65)


def test_lower_better_employee_policy_inverts_the_same_numbers():
    fixture = _load("july_august_attendance.json")
    july = achievement(fixture["actual"], fixture["july_target"], "lower_better", EMPLOYEE_POLICY)
    august = achievement(fixture["actual"], fixture["august_target"], "lower_better", EMPLOYEE_POLICY)

    # Actual 0.60 is worse than a 0.55 lower-better target, and better than 0.65.
    assert july.value == pytest.approx(0.55 / 0.6)
    assert july.raw_ratio == pytest.approx(0.55 / 0.6)
    assert august.value == 1.0
    assert august.raw_ratio == pytest.approx(0.65 / 0.6)


def test_csr_workbook_targets_follow_the_row_and_ignore_the_month_label():
    service = _service()
    july = _csr_row(0.55, "July")
    august = _csr_row(0.65, "August")
    july_again = _csr_row(0.55, "August")

    july_score, _, july_values = service.calculate_performance_multi_team("CSR", july)
    august_score, _, august_values = service.calculate_performance_multi_team("CSR", august)
    relabeled_score, _, relabeled_values = service.calculate_performance_multi_team("CSR", july_again)

    july_queries = next(item for item in july_values if item["kpi_key"] == "Queries")
    august_queries = next(item for item in august_values if item["kpi_key"] == "Queries")
    relabeled_queries = next(item for item in relabeled_values if item["kpi_key"] == "Queries")

    assert july_queries["achievement_ratio"] == 1.0
    assert july_queries["target_value"] == 0.55
    assert august_queries["target_value"] == 0.65
    assert august_queries["achievement_ratio"] == pytest.approx(round(0.6 / 0.65, 4))
    assert july_score == pytest.approx(100.0)
    assert august_score == pytest.approx((0.4 + (0.6 / 0.65) * 0.3 + 0.3) * 100.0)
    assert relabeled_score == july_score
    assert relabeled_queries["achievement_ratio"] == july_queries["achievement_ratio"]


def test_repeated_csr_inputs_keep_the_same_score():
    service = _service()
    first_score, first_grade, first_values = service.calculate_performance_multi_team("CSR", _csr_row(0.65, "August"))
    second_score, second_grade, second_values = service.calculate_performance_multi_team("CSR", _csr_row(0.65, "August"))

    assert (second_score, second_grade) == (first_score, first_grade)
    assert second_values == first_values


def test_coding_lower_better_uses_workbook_target_columns():
    service = _service()
    row = {
        "A.QualityErrorsRate": 0.08,
        "T.QualityErrorsRate": 0.05,
        "A.RejectionRate": 0.04,
        "T.RejectionRate": 0.04,
        "A.TAT": 2.5,
        "T.TAT": 2.5,
        "Month": "July",
    }
    score, _grade, values = service.calculate_performance_multi_team("Coding", row)
    quality = next(item for item in values if item["kpi_key"] == "QualityErrors")

    assert quality["direction"] == "lower_better"
    assert quality["achievement_ratio"] == pytest.approx(round(0.05 / 0.08, 4))
    assert score == pytest.approx((0.625 * 0.20 + 0.50 + 0.30) * 100.0)


def test_precomputed_achievement_ignores_target_and_direction_inputs():
    service = _service()
    config = resolve_team_config(
        load_team_config("Pre-Approvals IP Final Dubai"),
        "Employee",
        "Combined",
    )
    assert {kpi.get("score_formula") for kpi in config["kpis"]} == {"baseline_80"}

    def row_for(target: float, include_precomputed: bool) -> dict:
        row = {}
        for kpi in config["kpis"]:
            row[kpi["actual_col"]] = 0.60
            row[kpi["target_col"]] = target
            if include_precomputed:
                row[kpi["achievement_col"]] = 0.40
        return row

    raw_july, _, raw_july_values = service.calculate_performance_multi_team(
        "Pre-Approvals IP Final Dubai", row_for(0.55, False), "Employee", "Combined"
    )
    raw_august, _, raw_august_values = service.calculate_performance_multi_team(
        "Pre-Approvals IP Final Dubai", row_for(0.65, False), "Employee", "Combined"
    )
    pinned_july, _, pinned_july_values = service.calculate_performance_multi_team(
        "Pre-Approvals IP Final Dubai", row_for(0.55, True), "Employee", "Combined"
    )
    pinned_august, _, pinned_august_values = service.calculate_performance_multi_team(
        "Pre-Approvals IP Final Dubai", row_for(0.65, True), "Employee", "Combined"
    )

    assert raw_july_values[0]["achievement_ratio"] == 1.0
    assert raw_august_values[0]["achievement_ratio"] == pytest.approx(round(0.6 / 0.65, 4))
    assert raw_july != raw_august
    assert pinned_july == pinned_august
    assert {item["achievement_ratio"] for item in pinned_july_values} == {0.4}
    assert {item["achievement_ratio"] for item in pinned_august_values} == {0.4}


def test_missing_workbook_columns_fail_closed_for_config_scoring():
    service = _service()
    with pytest.raises(Exception, match="Missing Employee KPI columns"):
        service.calculate_performance_multi_team("CSR", {"Month": "July"})


def test_legacy_inbound_uses_repository_target_not_the_workbook_column():
    service = _service()
    assert DEFAULT_TARGETS["Inbound"]["Attend"] == 0.75

    def inbound_row(workbook_target: float, when: date) -> dict:
        return {
            "Date": when,
            "TotalHandledCalls": 100,
            "Dubai_Booking": 100,
            "Dubai_Attend": 60,
            "InboundCalls": 100,
            "AbandonedCalls": 0,
            "A.QualityScore": 0.95,
            "AHT_Minutes": 2.5,
            "T.Attend%": workbook_target,
            "Month": when.strftime("%B"),
        }

    _, _, july_achievements, july_weights = service.calculate_performance(
        "Inbound", inbound_row(0.55, date(2026, 7, 15))
    )
    _, _, august_achievements, august_weights = service.calculate_performance(
        "Inbound", inbound_row(0.65, date(2026, 8, 15))
    )
    _, _, june_achievements, june_weights = service.calculate_performance(
        "Inbound", inbound_row(0.55, date(2026, 6, 15))
    )

    assert july_achievements["Attend"] == pytest.approx(0.60 / 0.75)
    assert august_achievements["Attend"] == july_achievements["Attend"]
    assert june_achievements["Attend"] == july_achievements["Attend"]
    assert july_weights["Quality"] == pytest.approx(0.05)
    assert june_weights["Quality"] == 0.0
    assert june_weights["Other"] == pytest.approx(0.15)


def test_sales_raw_columns_change_with_target_until_only_precomputed_is_present():
    service = _service()
    raw_july, _, july_achievements, _weights = service.calculate_performance(
        "Sales",
        {"A.OPCensus": 60, "T.OPCensus": 55, "Month": "July"},
    )
    raw_august, _, august_achievements, _weights = service.calculate_performance(
        "Sales",
        {"A.OPCensus": 60, "T.OPCensus": 65, "Month": "August"},
    )
    precomputed_july, _, precomputed_july_achievements, _weights = service.calculate_performance(
        "Sales",
        {"OPCensusAch%": 0.40, "T.OPCensus": 55, "Month": "July"},
    )
    precomputed_august, _, precomputed_august_achievements, _weights = service.calculate_performance(
        "Sales",
        {"OPCensusAch%": 0.40, "T.OPCensus": 65, "Month": "August"},
    )

    assert july_achievements["OPCensus"] == pytest.approx(60 / 55)
    assert august_achievements["OPCensus"] == pytest.approx(60 / 65)
    assert raw_july != raw_august
    assert precomputed_july_achievements["OPCensus"] == pytest.approx(0.40)
    assert precomputed_august_achievements["OPCensus"] == pytest.approx(0.40)
    assert precomputed_july == precomputed_august
