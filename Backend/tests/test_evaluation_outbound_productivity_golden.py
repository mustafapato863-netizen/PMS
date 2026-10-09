"""Golden totals for anonymized Outbound July and August rates.

The public scoring engine is the system under test for the supported capped
ratio. Missing Productivity stays a fail-visible contract: these tests do not
upload a workbook, read a database, or activate D-004.
"""
from __future__ import annotations

import json
from datetime import time
from pathlib import Path

import pytest
from openpyxl.styles.numbers import BUILTIN_FORMATS, is_date_format
from openpyxl.utils.datetime import from_excel

from services.scoring.engine import (
    EMPLOYEE_POLICY,
    KPIResult,
    achievement,
    contribution,
    score,
    validate_weights,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "evaluation_baseline"
    / "outbound_august_productivity_golden.json"
)
TREND_SHA256 = "1a153df8957f2e4ba3001775419e2eab7b19c79cf14158876347b50ff442829d"
AUGUST_SOURCE_SHA256 = "62aad191081ca338a76cf3fbce8c267d1b517a6bbde3557dfe250ee80f1b2a68"
ABS_RATIO = 1e-15
ABS_SCORE = 1e-12


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _contract() -> dict:
    return _load(FIXTURE)


def _reference() -> dict:
    contract = _contract()
    return _load(ROOT / contract["reference_file"])


def _date_aware_time_reading(day_fraction: float) -> str:
    """Reproduce the library interpretation, not native Excel rendering."""
    assert BUILTIN_FORMATS[22] == "m/d/yy h:mm"
    assert is_date_format(BUILTIN_FORMATS[22])
    interpreted = from_excel(day_fraction)
    assert isinstance(interpreted, time)
    return interpreted.isoformat(timespec="seconds")


def _score_month(actuals: dict, targets: dict, weights: dict):
    """Score stored inputs. A missing actual is refused here rather than zero-filled."""
    validate_weights(weights)
    details = {}
    results = []
    for key, weight in weights.items():
        actual = actuals[key]
        target = targets[key]
        if actual is None or target is None:
            raise AssertionError(
                f"{key} has no stored input. Missing Productivity fails visibly "
                "and is not scored as zero."
            )
        result = achievement(actual, target, "higher_better", EMPLOYEE_POLICY)
        weighted = contribution(result.value, weight)
        details[key] = {"achievement": result, "contribution": weighted}
        results.append(KPIResult(achievement=result.value, weight=weight, contribution=weighted))
    return details, score(results)


def _assert_ratio(actual: float, target: float, stored_achievement: float, result) -> None:
    assert result.state == "measured"
    assert result.raw_ratio == pytest.approx(actual / target, abs=ABS_RATIO)
    assert result.value == min(result.raw_ratio, 1.0)
    assert result.value == pytest.approx(stored_achievement, abs=ABS_RATIO)
    if actual > target:
        assert result.value == 1.0
        assert result.raw_ratio > 1.0


def test_supplied_achievements_sum_to_the_reference_totals():
    reference = _reference()
    for period, achievement_key in (
        (reference["july"], "validated_stored_achievements"),
        (reference["august"], "expected_achievements"),
    ):
        total = sum(
            period[achievement_key][key] * weight
            for key, weight in period["weights"].items()
        )
        assert total == pytest.approx(period["expected_score"], abs=ABS_RATIO)
        validate_weights(period["weights"])


def test_engine_reproduces_july_and_august_totals():
    reference = _reference()
    july = reference["july"]
    august = reference["august"]

    july_details, july_total = _score_month(july["actuals"], july["targets"], july["weights"])
    august_details, august_total = _score_month(
        august["actuals"], august["targets"], august["weights"]
    )

    for period, details, total, achievement_key in (
        (july, july_details, july_total, "validated_stored_achievements"),
        (august, august_details, august_total, "expected_achievements"),
    ):
        for key, weight in period["weights"].items():
            _assert_ratio(
                period["actuals"][key],
                period["targets"][key],
                period[achievement_key][key],
                details[key]["achievement"],
            )
            assert details[key]["contribution"] == pytest.approx(
                period[achievement_key][key] * weight,
                abs=ABS_RATIO,
            )
        assert total.earned == pytest.approx(period["expected_score"], abs=ABS_RATIO)
        assert total.score == pytest.approx(period["expected_score"] * 100.0, abs=ABS_SCORE)
        assert total.state == "measured"
        assert total.coverage == 1.0
        assert total.configured_weight == pytest.approx(1.0, abs=1e-9)

    assert july_total.earned != pytest.approx(august_total.earned, abs=1e-9)
    assert set(july_details) == {"Booking", "Attendance", "Reachability", "Quality"}
    assert set(august_details) == set(july_details) | {"Productivity"}


def test_month_kpi_sets_stay_separate():
    reference = _reference()
    contract = _contract()
    july = reference["july"]
    august = reference["august"]

    assert july["targets"]["Attendance"] == 0.65
    assert august["targets"]["Attendance"] == 0.65
    assert contract["source_timeline"]["july_55_august_65_is_source_history"] is False
    assert july["weights"]["Attendance"] == 0.7
    assert august["weights"]["Attendance"] == 0.6
    assert august["weights"]["Productivity"] == 0.1
    assert august["targets"]["Productivity"] == 0.8
    assert "Productivity" not in july["actuals"]
    assert "Productivity" not in july["targets"]
    assert "Productivity" not in july["weights"]
    assert [key for key in august["weights"] if key not in july["actuals"]] == ["Productivity"]

    shifted = dict(july["weights"])
    shifted["Attendance"] = august["weights"]["Attendance"]
    with pytest.raises(ValueError, match="1.0"):
        validate_weights(shifted)

    combined = dict(july["weights"])
    combined["Productivity"] = august["weights"]["Productivity"]
    with pytest.raises(ValueError, match="1.0"):
        validate_weights(combined)


def test_synthetic_55_65_scenario_preserves_each_month_kpi_set():
    reference = _reference()
    contract = _contract()
    scenario = contract["synthetic_attendance_scenario"]
    july = reference["july"]
    august = reference["august"]

    assert scenario["status"] == "acceptance_scenario_not_source_history"
    assert scenario["july_attendance_target"] == 0.55
    assert scenario["august_attendance_target"] == 0.65
    assert july["targets"]["Attendance"] != scenario["july_attendance_target"]

    synthetic_targets = dict(july["targets"])
    synthetic_targets["Attendance"] = scenario["july_attendance_target"]
    details, total = _score_month(july["actuals"], synthetic_targets, july["weights"])
    attendance = details["Attendance"]["achievement"]

    assert "Productivity" not in details
    assert attendance.raw_ratio == pytest.approx(
        scenario["july_expected_attendance_raw_ratio"],
        abs=ABS_RATIO,
    )
    assert attendance.value == scenario["july_expected_attendance_achievement"]
    assert attendance.value == 1.0
    assert attendance.raw_ratio > 1.0
    for key, expected in scenario["july_expected_contributions"].items():
        assert details[key]["contribution"] == pytest.approx(expected, abs=ABS_RATIO)
    assert total.earned == pytest.approx(scenario["july_expected_score"], abs=ABS_RATIO)
    assert total.score == pytest.approx(scenario["july_expected_score"] * 100.0, abs=ABS_SCORE)
    assert total.earned != pytest.approx(july["expected_score"], abs=1e-9)

    _, august_total = _score_month(august["actuals"], august["targets"], august["weights"])
    assert august["targets"]["Attendance"] == scenario["august_attendance_target"]
    assert august_total.earned == pytest.approx(august["expected_score"], abs=ABS_RATIO)
    assert "Productivity" in august["weights"]


def test_cap_boundaries_use_the_supported_ratio():
    contract = _contract()
    for boundary in contract["cap_boundaries"]:
        result = achievement(
            boundary["actual"],
            boundary["target"],
            "higher_better",
            EMPLOYEE_POLICY,
        )
        weighted = contribution(result.value, 0.1)
        assert result.state == boundary["expected_state"]
        assert result.raw_ratio == pytest.approx(boundary["expected_raw_ratio"], abs=ABS_RATIO)
        assert result.value == pytest.approx(boundary["expected_value"], abs=ABS_RATIO)
        assert weighted == pytest.approx(boundary["expected_value"] * 0.1, abs=ABS_RATIO)

    reference = _reference()
    capped = {
        ("july", "Quality"),
        ("august", "Booking"),
        ("august", "Quality"),
    }
    for period_name, key in capped:
        period = reference[period_name]
        result = achievement(
            period["actuals"][key],
            period["targets"][key],
            "higher_better",
            EMPLOYEE_POLICY,
        )
        assert result.value == 1.0
        assert result.raw_ratio > 1.0

    productivity = reference["august"]
    under_cap = achievement(
        productivity["actuals"]["Productivity"],
        productivity["targets"]["Productivity"],
        "higher_better",
        EMPLOYEE_POLICY,
    )
    assert under_cap.value < 1.0
    assert under_cap.value == pytest.approx(
        productivity["expected_achievements"]["Productivity"],
        abs=ABS_RATIO,
    )


def test_attendance_target_stays_the_raw_ratio():
    reference = _reference()
    contract = _contract()
    serialized = contract["attendance_target_serialization"]
    august = reference["august"]
    actual = august["actuals"]["Attendance"]
    raw_target = serialized["required_scoring_value"]

    assert serialized["raw_numeric"] == 0.65
    assert serialized["excel_builtin_format_id"] == 22
    assert raw_target == august["targets"]["Attendance"]
    assert _date_aware_time_reading(raw_target) == serialized["date_aware_display"]
    assert _date_aware_time_reading(raw_target) == "15:36:00"

    certified = achievement(actual, raw_target, "higher_better", EMPLOYEE_POLICY)
    as_hours = achievement(actual, raw_target * 24.0, "higher_better", EMPLOYEE_POLICY)
    as_minutes = achievement(actual, raw_target * 24.0 * 60.0, "higher_better", EMPLOYEE_POLICY)

    assert certified.value == pytest.approx(
        august["expected_achievements"]["Attendance"],
        abs=ABS_RATIO,
    )
    assert as_hours.value != pytest.approx(certified.value, abs=1e-6)
    assert as_minutes.value != pytest.approx(certified.value, abs=1e-6)
    assert "magnitude_heuristic" in serialized["rejected_readings"]


def test_missing_productivity_substitutions_do_not_match_august():
    reference = _reference()
    contract = _contract()
    august = reference["august"]
    missing = contract["missing_productivity"]
    _, certified = _score_month(august["actuals"], august["targets"], august["weights"])

    assert missing["august_actual"] is None
    assert missing["disposition"] == "fail_visible_missing_source_actual"
    assert set(missing["forbidden_substitutions"]) == {
        "zero",
        "renormalize_remaining_weights",
        "infer_from_available_time",
        "infer_from_final_score",
        "trend_lookup",
    }

    zero_filled = dict(august["actuals"])
    zero_filled["Productivity"] = 0.0
    zero_details, zero_total = _score_month(zero_filled, august["targets"], august["weights"])
    assert zero_details["Productivity"]["achievement"].value == 0.0
    assert zero_details["Productivity"]["achievement"].state == "measured"
    assert zero_total.earned != pytest.approx(certified.earned, abs=1e-9)

    remaining_weights = {
        key: weight for key, weight in august["weights"].items() if key != "Productivity"
    }
    remaining_actuals = {
        key: value for key, value in august["actuals"].items() if key != "Productivity"
    }
    remaining_targets = {
        key: value for key, value in august["targets"].items() if key != "Productivity"
    }
    with pytest.raises(ValueError, match="1.0"):
        validate_weights(remaining_weights)
    # The public aggregate rescales a shorter measured set. That rescaled
    # result is a different KPI set, not the certified August total.
    partial_results = []
    for key, weight in remaining_weights.items():
        result = achievement(
            remaining_actuals[key],
            remaining_targets[key],
            "higher_better",
            EMPLOYEE_POLICY,
        )
        partial_results.append(KPIResult(achievement=result.value, weight=weight))
    partial = score(partial_results)
    assert partial.earned != pytest.approx(certified.earned, abs=1e-9)
    assert partial.score != pytest.approx(certified.score, abs=1e-6)


def test_aht_is_diagnostic_and_outside_the_scored_total():
    reference = _reference()
    contract = _contract()
    aht = contract["aht"]

    assert aht["included_in_scored_total"] is False
    assert aht["enabled"] is False
    assert aht["weight"] == 0.0
    assert aht["target_seconds"] == 150
    assert "AHT" not in reference["july"]["weights"]
    assert "AHT" not in reference["august"]["weights"]
    validate_weights(reference["july"]["weights"])
    validate_weights(reference["august"]["weights"])


def test_characterization_records_hashes_and_closed_gates():
    contract = _contract()
    reference = _reference()

    assert contract["status"] == "source_characterization_only_not_activated"
    assert reference["status"] == "source_reference_only_not_activated"
    assert contract["provenance"]["trend_sha256"] == TREND_SHA256
    assert contract["provenance"]["august_source_sha256"] == AUGUST_SOURCE_SHA256
    assert len(TREND_SHA256) == 64
    assert len(AUGUST_SOURCE_SHA256) == 64
    assert contract["decisions"]["d004"] == "approved_intention_only_not_activated"
    assert contract["policy"]["grades"] == "unavailable_external_table_not_asserted"
    assert contract["ingestion_gates"] == [
        "preserve_raw_percentage_0.65",
        "reject_excel_builtin_22_time_reading",
        "reject_magnitude_heuristic",
        "do_not_derive_productivity_from_available_time",
        "fail_visible_when_august_productivity_actual_is_missing",
        "do_not_zero_fill_missing_productivity",
        "do_not_accept_trend_as_the_productivity_source",
        "do_not_apply_the_august_kpi_set_to_july",
        "keep_aht_diagnostic_and_weight_zero",
        "do_not_add_grade_bands_or_treat_a_cached_label_as_policy",
        "confirm_productivity_survives_workbook_crop_before_ingestion",
        "block_approved_fixed_target_conflicts_with_no_bypass",
    ]
    assert "zero_denominator_defaults" in contract["not_invented"]
