"""Scoring-basis comparison uses stored pinned rules, not version identity."""
import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = ""

from models.schemas import EvaluationData, PerformanceRecord
from services.planning_service import PlanningService
from services.scoring_basis_comparison import compare_adjacent_records, compare_scoring_basis


def _kpi(key="Attendance", **overrides):
    row = {
        "kpi_key": key,
        "target_value": 0.65,
        "weight_applied": 0.70,
        "direction": "higher_better",
        "unit": "%",
        "actual_value": 0.60,
        "evaluation_pinned": True,
    }
    row.update(overrides)
    return row


def _record(employee, month, team="Outbound", kpis=None, year=2026, **extra):
    payload = {
        "employee_id": employee,
        "employee_name": employee,
        "month": month,
        "year": year,
        "team": team,
        "position": "Agent",
        "performance_level": "Employee",
        "kpi_values": kpis if kpis is not None else [_kpi()],
    }
    payload.update(extra)
    return payload


def _populations():
    july = [_record("A", "July")]
    august = [_record("A", "August", kpis=[_kpi(target_value=0.65, weight_applied=0.60, actual_value=0.60)])]
    return july, august


def test_target_or_weight_change_warns_without_claiming_a_raw_change():
    july = [_record("A", "July", kpis=[_kpi(actual_value=0.60, target_value=0.55, weight_applied=0.70)])]
    august = [_record("A", "August", kpis=[_kpi(actual_value=0.60, target_value=0.65, weight_applied=0.60)])]
    result = compare_scoring_basis(august, july)

    assert result["state"] == "changed"
    assert result["like_for_like"] is False
    assert result["raw_performance"] == "unchanged"
    assert "target" in result["reasons"]
    assert "weight" in result["reasons"]
    assert "Scores can be affected by evaluation settings." in result["message"]
    assert "Comparable raw performance is unchanged." in result["message"]
    assert "caused" not in result["message"].casefold()
    assert "0.65" not in result["message"]


def test_raw_change_on_the_same_rules_is_not_a_basis_warning():
    july = [_record("A", "July", kpis=[_kpi(actual_value=0.60)])]
    august = [_record("A", "August", kpis=[_kpi(actual_value=0.40)])]
    result = compare_scoring_basis(august, july)

    assert result["state"] == "unchanged"
    assert result["like_for_like"] is True
    assert result["raw_performance"] == "changed"
    assert result["message"] is None
    assert result["reasons"] == []


def test_identical_rules_with_a_different_version_are_not_changed():
    july = [_record("A", "July", version_id="version-july", rules_checksum="aaa")]
    august = [_record("A", "August", version_id="version-august", rules_checksum="bbb")]
    result = compare_adjacent_records([*july, *august], year=2026, month="August", team="Outbound")

    assert result["state"] == "unchanged"
    assert result["message"] is None
    assert "version" not in result["reasons"]


def test_reordered_kpi_keys_match():
    july = [_record("A", "July", kpis=[_kpi("Attendance"), _kpi("Quality", target_value=90, weight_applied=0.30, actual_value=88, unit="score")])]
    august = [_record("A", "August", kpis=[_kpi("Quality", target_value=90, weight_applied=0.30, actual_value=88, unit="score"), _kpi("Attendance")])]
    result = compare_scoring_basis(august, july)

    assert result["state"] == "unchanged"
    assert result["reasons"] == []


def test_mixed_direction_inside_one_scope_is_not_like_for_like():
    july = [
        _record("A", "July", kpis=[_kpi(direction="higher_better")]),
        _record("B", "July", kpis=[_kpi(direction="lower_better")]),
    ]
    august = [
        _record("A", "August", kpis=[_kpi(direction="higher_better", actual_value=0.50)]),
        _record("B", "August", kpis=[_kpi(direction="lower_better", actual_value=0.50)]),
    ]
    result = compare_scoring_basis(august, july)

    assert result["state"] == "mixed"
    assert result["like_for_like"] is False
    assert result["raw_performance"] == "not_comparable"
    assert "not like-for-like" in result["message"]
    assert "Scores can be affected by evaluation settings." in result["message"]


def test_added_kpi_is_a_set_change_and_does_not_invent_the_missing_month():
    july = [_record("A", "July", kpis=[_kpi("Attendance", actual_value=0.60)])]
    august = [_record("A", "August", kpis=[
        _kpi("Attendance", actual_value=0.60),
        _kpi("Productivity", target_value=10, weight_applied=0.10, actual_value=8, unit="count"),
    ])]
    result = compare_scoring_basis(august, july)

    assert result["state"] == "changed"
    assert result["reasons"] == ["kpi_set"]
    assert result["raw_performance"] == "partial"
    assert "Shared comparable KPI values are unchanged." in result["message"]
    assert "Comparable raw performance is unchanged." not in result["message"]
    assert "Some KPI actuals are not comparable." in result["message"]
    assert "Productivity" not in str(result)
    assert result.get("previous_rules", {}).get("productivity") is None


def test_membership_change_alone_is_not_a_rule_change():
    july = [_record("A", "July", kpis=[_kpi(actual_value=0.60)])]
    august = [_record("B", "August", kpis=[_kpi(actual_value=0.40)])]
    result = compare_scoring_basis(august, july)

    assert result["state"] == "unchanged"
    assert result["like_for_like"] is False
    assert result["reasons"] == []
    assert result["raw_performance"] == "unknown"
    assert "population changed" in result["message"].casefold()
    assert "evaluation settings" not in result["message"].casefold()
    assert "kpi values changed" not in result["message"].casefold()


def test_missing_pin_is_unknown_and_does_not_assert_unchanged():
    july = [_record("A", "July", kpis=[_kpi(evaluation_pinned=False)])]
    august = [_record("A", "August", kpis=[_kpi(evaluation_pinned=False, target_value=0.90)])]
    result = compare_scoring_basis(august, july)

    assert result["state"] == "unknown"
    assert result["like_for_like"] is False
    assert result["raw_performance"] == "unknown"
    assert result["message"]
    assert "unchanged" not in result["message"].casefold()
    assert "Scores can be affected" not in result["message"]


def test_version_checksum_without_pinned_rules_is_not_a_change():
    july = [_record("A", "July", kpis=[], version_id="v1", rules_checksum="one")]
    august = [_record("A", "August", kpis=[], version_id="v2", rules_checksum="two")]
    result = compare_scoring_basis(august, july)

    assert result["state"] == "unknown"
    assert result["reasons"] == []


def test_other_team_and_non_adjacent_month_do_not_leak():
    records = [
        _record("A", "June", team="Outbound", kpis=[_kpi(target_value=0.10)]),
        _record("A", "August", team="Outbound", kpis=[_kpi(target_value=0.65)]),
        _record("B", "July", team="Inbound", kpis=[_kpi(target_value=0.20)]),
        _record("B", "August", team="Inbound", kpis=[_kpi(target_value=0.80)]),
    ]
    outbound = compare_adjacent_records(records, year=2026, month="August", team="Outbound")
    inbound = compare_adjacent_records(records, year=2026, month="August", team="Inbound")

    assert outbound["state"] == "unavailable"
    assert "June" not in str(outbound["message"])
    assert inbound["state"] == "changed"
    assert inbound["reasons"] == ["target"]


def test_explicit_formula_difference_is_a_rule_change_and_absent_formula_is_not_invented():
    july = [_record("A", "July", kpis=[_kpi(formula="target_ratio")])]
    august = [_record("A", "August", kpis=[_kpi(formula="capped_ratio")])]
    changed = compare_scoring_basis(august, july)
    silent = compare_scoring_basis(
        [_record("A", "August")],
        [_record("A", "July", kpis=[_kpi(formula="target_ratio")])],
    )

    assert changed["state"] == "changed"
    assert changed["reasons"] == ["formula"]
    assert silent["state"] == "unknown"
    assert silent["like_for_like"] is False
    assert "unchanged" not in silent["message"].casefold()


def test_percent_scale_is_not_rewritten_before_comparison():
    july = [_record("A", "July", kpis=[_kpi(target_value=0.65, unit="%")])]
    august = [_record("A", "August", kpis=[_kpi(target_value=65, unit="%")])]
    result = compare_scoring_basis(august, july)

    assert result["state"] == "changed"
    assert result["reasons"] == ["target"]


def _plan_record(employee, month, score, target, attend=0.90):
    return PerformanceRecord(
        id=f"{employee}-2026-{month}",
        employee_id=employee,
        employee_name=employee,
        team="Outbound",
        month=month,
        year=2026,
        position="Agent",
        performance_level="Employee",
        evaluation=EvaluationData(score=score, grade="C"),
        actual={"attend_rate": attend},
        kpi_values=[_kpi(target_value=target, actual_value=0.60)],
    )


def test_planning_categories_stay_put_when_the_basis_warning_is_added():
    records = [
        _plan_record("A", "July", 90, 0.55),
        _plan_record("A", "August", 70, 0.65),
    ]
    service = PlanningService(performance_repo=None)
    before = service.classify_records(records, month="August", year=2026)
    context = compare_adjacent_records(records, year=2026, month="August")
    after = service.classify_records(records, month="August", year=2026)

    assert [row.employee_id for row in before["Attrition Risk"]] == ["A"]
    assert [row.employee_id for row in after["Attrition Risk"]] == ["A"]
    assert [row.employee_id for row in before["Reward Candidate"]] == [row.employee_id for row in after["Reward Candidate"]]
    assert context["state"] == "changed"
    assert "Scores can be affected by evaluation settings." in context["message"]
    assert context["raw_performance"] == "unchanged"


def test_planning_same_rules_do_not_add_a_basis_warning():
    records = [
        _plan_record("A", "July", 90, 0.65),
        _plan_record("A", "August", 70, 0.65),
    ]
    context = compare_adjacent_records(records, year=2026, month="August")

    assert context["state"] == "unchanged"
    assert context["like_for_like"] is True
    assert context["message"] is None


def test_no_overlapping_scope_is_not_like_for_like():
    result = compare_scoring_basis(
        [_record("A", "August", team="Inbound")],
        [_record("A", "July", team="Outbound")],
    )

    assert result["state"] == "unknown"
    assert result["like_for_like"] is False
    assert result["raw_performance"] == "unknown"
    assert "unchanged" not in result["message"].casefold()
    assert "Scores can be affected" not in result["message"]


def test_joiner_does_not_prove_the_population_raw_is_unchanged():
    july = [_record("A", "July", kpis=[_kpi(actual_value=0.60)])]
    august = [
        _record("A", "August", kpis=[_kpi(actual_value=0.60)]),
        _record("B", "August", kpis=[_kpi(actual_value=0.10)]),
    ]
    result = compare_scoring_basis(august, july)

    assert result["state"] == "unchanged"
    assert result["reasons"] == []
    assert result["like_for_like"] is False
    assert result["raw_performance"] == "partial"
    assert "population changed" in result["message"].casefold()
    assert "Shared comparable KPI values are unchanged." in result["message"]
    assert "Comparable raw performance is unchanged." not in result["message"]


def test_partial_actuals_do_not_claim_all_raw_performance_is_unchanged():
    quality = dict(target_value=90, weight_applied=0.30, unit="score")
    july = [_record("A", "July", kpis=[_kpi("Attendance", actual_value=0.60), _kpi("Quality", actual_value=80, **quality)])]
    august = [_record("A", "August", kpis=[_kpi("Attendance", actual_value=0.60), _kpi("Quality", actual_value=None, **quality)])]
    result = compare_scoring_basis(august, july)

    assert result["state"] == "unchanged"
    assert result["like_for_like"] is False
    assert result["raw_performance"] == "partial"
    assert "Shared comparable KPI values are unchanged." in result["message"]
    assert "Comparable raw performance is unchanged." not in result["message"]
    assert "Some KPI actuals are not comparable." in result["message"]


def test_unit_mismatch_is_not_hidden_by_another_unchanged_kpi():
    july = [_record("A", "July", kpis=[
        _kpi("Attendance", actual_value=0.60),
        _kpi("Quality", target_value=90, weight_applied=0.30, actual_value=80, unit="score"),
    ])]
    august = [_record("A", "August", kpis=[
        _kpi("Attendance", actual_value=0.60),
        _kpi("Quality", target_value=90, weight_applied=0.30, actual_value=80, unit="percent"),
    ])]
    result = compare_scoring_basis(august, july)

    assert result["state"] == "changed"
    assert "unit" in result["reasons"]
    assert result["raw_performance"] == "partial"
    assert "not comparable" in result["message"].casefold()
    assert "Shared comparable KPI values are unchanged." in result["message"]


def test_non_finite_boolean_and_invalid_direction_do_not_crash_or_default():
    invalid_target = compare_scoring_basis(
        [_record("A", "August", kpis=[_kpi(target_value=float("nan"))])],
        [_record("A", "July", kpis=[_kpi(target_value=float("inf"))])],
    )
    boolean_weight = compare_scoring_basis(
        [_record("A", "August", kpis=[_kpi(weight_applied=True)])],
        [_record("A", "July", kpis=[_kpi(weight_applied=False)])],
    )
    invalid_direction = compare_scoring_basis(
        [_record("A", "August", kpis=[_kpi(direction="sideways")])],
        [_record("A", "July")],
    )
    missing_actual = compare_scoring_basis(
        [_record("A", "August", kpis=[_kpi(actual_value=float("nan"))])],
        [_record("A", "July", kpis=[_kpi(actual_value=0.60)])],
    )

    assert invalid_target["state"] == "unknown"
    assert invalid_target["like_for_like"] is False
    assert boolean_weight["state"] == "unknown"
    assert invalid_direction["state"] == "unknown"
    assert invalid_direction["like_for_like"] is False
    assert "higher_better" not in str(invalid_direction["message"])
    assert missing_actual["state"] == "unchanged"
    assert missing_actual["raw_performance"] == "unknown"
    assert missing_actual["like_for_like"] is False
    assert "unchanged" not in (missing_actual["message"] or "").casefold()


def test_one_sided_source_is_unknown_and_both_absent_stays_comparable():
    one_sided = compare_scoring_basis(
        [_record("A", "August")],
        [_record("A", "July", kpis=[_kpi(source="upload")])],
    )
    both_absent = compare_scoring_basis([_record("A", "August")], [_record("A", "July")])

    assert one_sided["state"] == "unknown"
    assert one_sided["like_for_like"] is False
    assert "unchanged" not in one_sided["message"].casefold()
    assert both_absent["state"] == "unchanged"
    assert both_absent["like_for_like"] is True
    assert both_absent["message"] is None


def test_added_team_scope_does_not_claim_the_whole_population_is_like_for_like():
    result = compare_scoring_basis(
        [_record("A", "August"), _record("B", "August", team="Inbound")],
        [_record("A", "July")],
    )
    assert result["like_for_like"] is False
    assert result["raw_performance"] not in {"unchanged", "changed"}
    assert result["message"]


def test_valid_team_scope_does_not_require_an_optional_position():
    result = compare_scoring_basis(
        [_record("A", "August", team="Coding", position="", performance_level="Employee")],
        [_record("A", "July", team="Coding", position="", performance_level="Employee")],
    )
    separated = compare_scoring_basis(
        [_record("A", "August", team="Coding", position="", performance_level="Employee")],
        [_record("A", "July", team="Coding", position="Agent", performance_level="Employee")],
    )

    assert result["state"] == "unchanged"
    assert result["like_for_like"] is True
    assert separated["like_for_like"] is False


def test_unidentified_extra_scope_is_not_silently_discarded():
    current = [
        _record("A", "August", team="Coding", position="Agent", performance_level="Employee"),
        _record("B", "August", team="", position="Agent", performance_level=""),
    ]
    previous = [_record("A", "July", team="Coding", position="Agent", performance_level="Employee")]
    result = compare_scoring_basis(current, previous)

    assert result["like_for_like"] is False
    assert result["raw_performance"] != "unchanged"


def test_missing_scope_identity_does_not_create_a_trusted_shared_scope():
    result = compare_scoring_basis(
        [_record("A", "August", team="", position="", performance_level="")],
        [_record("A", "July", team="", position="", performance_level="")],
    )
    assert result["like_for_like"] is False
    assert result["state"] in {"unknown", "unavailable"}


def test_explicit_source_change_is_not_proof_of_comparable_raw_observations():
    result = compare_scoring_basis(
        [_record("A", "August", kpis=[_kpi(source="system_b")])],
        [_record("A", "July", kpis=[_kpi(source="system_a")])],
    )
    assert result["state"] == "changed"
    assert result["raw_performance"] not in {"unchanged", "changed"}
    assert "Comparable raw performance is unchanged." not in (result["message"] or "")


def test_scientific_notation_and_negative_zero_match_without_percent_rescaling():
    tiny = compare_scoring_basis(
        [_record("A", "August", kpis=[_kpi(target_value="1e-7", actual_value="1E-7")])],
        [_record("A", "July", kpis=[_kpi(target_value="0.0000001", actual_value=1e-7)])],
    )
    large = compare_scoring_basis(
        [_record("A", "August", kpis=[_kpi(target_value="1e+21", actual_value="1e21")])],
        [_record("A", "July", kpis=[_kpi(target_value="1000000000000000000000", actual_value=10**21)])],
    )
    negative_zero = compare_scoring_basis(
        [_record("A", "August", kpis=[_kpi(target_value="-0", actual_value="-0.0")])],
        [_record("A", "July", kpis=[_kpi(target_value=0, actual_value="0")])],
    )
    scale = compare_scoring_basis(
        [_record("A", "August", kpis=[_kpi(target_value="0.65")])],
        [_record("A", "July", kpis=[_kpi(target_value="65")])],
    )

    assert tiny["state"] == "unchanged" and tiny["like_for_like"] is True
    assert large["state"] == "unchanged" and large["like_for_like"] is True
    assert negative_zero["state"] == "unchanged" and negative_zero["like_for_like"] is True
    assert scale["state"] == "changed" and scale["reasons"] == ["target"]
