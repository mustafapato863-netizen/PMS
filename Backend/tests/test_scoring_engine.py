import math
import pytest
from services.scoring.engine import (
    AchievementResult,
    ScoreResult,
    KPIResult,
    EMPLOYEE_POLICY,
    ROLLUP_POLICY,
    MANAGEMENT_POLICY,
    FUNCTION_POLICY,
    achievement,
    contribution,
    score,
    status,
    grade,
    validate_weights,
)


class TestEmployeePolicy:
    """Tests for EMPLOYEE_POLICY reproducing kpi_service."""

    def test_normal_and_overachievement(self):
        # higher_better: actual=80, target=100 -> 0.8
        res = achievement(80, 100, "higher_better", EMPLOYEE_POLICY)
        assert res.value == 0.8
        assert res.state == "measured"

        # higher_better: actual=120, target=100 -> 1.0 (capped)
        res = achievement(120, 100, "higher_better", EMPLOYEE_POLICY)
        assert res.value == 1.0
        assert res.state == "measured"

        # lower_better: actual=80, target=100 -> target/actual = 1.25 -> capped at 1.0
        res = achievement(80, 100, "lower_better", EMPLOYEE_POLICY)
        assert res.value == 1.0
        assert res.state == "measured"

        # lower_better: actual=120, target=100 -> 100/120 = 0.8333
        res = achievement(120, 100, "lower_better", EMPLOYEE_POLICY)
        assert pytest.approx(res.value, rel=1e-5) == 0.8333333333333334
        assert res.state == "measured"

    def test_edge_cases(self):
        # actual=0, higher_better -> 0.0
        res = achievement(0, 100, "higher_better", EMPLOYEE_POLICY)
        assert res.value == 0.0
        assert res.state == "measured"

        # actual=0, lower_better -> 1.0 (zero_actual_value)
        res = achievement(0, 100, "lower_better", EMPLOYEE_POLICY)
        assert res.value == 1.0
        assert res.state == "measured"

        # target=0, higher_better -> 0.0
        res = achievement(80, 0, "higher_better", EMPLOYEE_POLICY)
        assert res.value == 0.0
        assert res.state == "invalid_target"

        # target=0, lower_better -> 0.0
        res = achievement(80, 0, "lower_better", EMPLOYEE_POLICY)
        assert res.value == 0.0

        # actual=0, target=0, higher_better -> 0.0
        res = achievement(0, 0, "higher_better", EMPLOYEE_POLICY)
        assert res.value == 0.0

        # actual=0, target=0, lower_better -> 1.0
        res = achievement(0, 0, "lower_better", EMPLOYEE_POLICY)
        assert res.value == 1.0

        # negative actual, higher_better -> 0.0
        res = achievement(-10, 100, "higher_better", EMPLOYEE_POLICY)
        assert res.value == 0.0
        assert res.state == "negative_actual"

        # negative actual, lower_better -> 0.0
        res = achievement(-10, 100, "lower_better", EMPLOYEE_POLICY)
        assert res.value == 0.0
        assert res.state == "negative_actual"

        # None actual, higher_better -> 0.0
        res = achievement(None, 100, "higher_better", EMPLOYEE_POLICY)
        assert res.value == 0.0
        assert res.state == "missing_actual"

        # None actual, lower_better -> 1.0
        res = achievement(None, 100, "lower_better", EMPLOYEE_POLICY)
        assert res.value == 1.0
        assert res.state == "missing_actual"

        # None target -> 0.0
        res = achievement(80, None, "higher_better", EMPLOYEE_POLICY)
        assert res.value == 0.0
        assert res.state == "invalid_target"


class TestRollupPolicy:
    """Tests for ROLLUP_POLICY reproducing kpi_aggregation.capped_achievement."""

    def test_normal_and_overachievement(self):
        # higher_better: 80/100 -> 0.8
        res = achievement(80, 100, "higher_better", ROLLUP_POLICY)
        assert res.value == 0.8
        assert res.state == "measured"

        # higher_better over: 120/100 -> 1.0
        res = achievement(120, 100, "higher_better", ROLLUP_POLICY)
        assert res.value == 1.0
        assert res.state == "measured"

        # lower_better: 80/100 -> 1.0
        res = achievement(80, 100, "lower_better", ROLLUP_POLICY)
        assert res.value == 1.0
        assert res.state == "measured"

        # lower_better: 120/100 -> 100/120 = 0.8333
        res = achievement(120, 100, "lower_better", ROLLUP_POLICY)
        assert pytest.approx(res.value, rel=1e-5) == 0.8333333333333334
        assert res.state == "measured"

    def test_edge_cases(self):
        # target <= 0 -> None
        assert achievement(80, 0, "higher_better", ROLLUP_POLICY).value is None
        assert achievement(80, -5, "higher_better", ROLLUP_POLICY).value is None
        assert achievement(80, 0, "lower_better", ROLLUP_POLICY).value is None

        # None actual or target -> None
        assert achievement(None, 100, "higher_better", ROLLUP_POLICY).value is None
        assert achievement(80, None, "higher_better", ROLLUP_POLICY).value is None

        # Unknown direction -> None
        assert achievement(80, 100, "sideways", ROLLUP_POLICY).value is None
        assert achievement(80, 100, None, ROLLUP_POLICY).value is None

        # actual <= 0, lower_better -> 1.0
        res_zero = achievement(0, 100, "lower_better", ROLLUP_POLICY)
        assert res_zero.value == 1.0
        res_neg = achievement(-10, 100, "lower_better", ROLLUP_POLICY)
        assert res_neg.value == 1.0

        # negative actual, higher_better -> 0.0
        res_neg_hi = achievement(-10, 100, "higher_better", ROLLUP_POLICY)
        assert res_neg_hi.value == 0.0
        assert res_neg_hi.state == "negative_actual"


class TestManagementPolicy:
    """Tests for MANAGEMENT_POLICY reproducing management_bsc._direction_ratio."""

    def test_normal_and_overachievement(self):
        # higher_better: uncapped! 120/100 -> 1.2
        res = achievement(120, 100, "higher_better", MANAGEMENT_POLICY)
        assert res.value == 1.2
        assert res.state == "measured"

        # lower_better: uncapped! 50/100 -> 100/50 = 2.0
        res = achievement(50, 100, "lower_better", MANAGEMENT_POLICY)
        assert res.value == 2.0
        assert res.state == "measured"

    def test_edge_cases(self):
        # actual=0, lower_better: None if target!=0, 1.0 if target==0
        assert achievement(0, 100, "lower_better", MANAGEMENT_POLICY).value is None
        assert achievement(0, 0, "lower_better", MANAGEMENT_POLICY).value == 1.0

        # target=0, higher_better: None if actual!=0, 1.0 if actual==0
        assert achievement(80, 0, "higher_better", MANAGEMENT_POLICY).value is None
        assert achievement(0, 0, "higher_better", MANAGEMENT_POLICY).value == 1.0

        # negative actual: returns negative ratio
        res_hi = achievement(-10, 100, "higher_better", MANAGEMENT_POLICY)
        assert res_hi.value == -0.1
        assert res_hi.state == "negative_actual"

        res_lo = achievement(-10, 100, "lower_better", MANAGEMENT_POLICY)
        assert res_lo.value == -10.0
        assert res_lo.state == "negative_actual"

        # None actual or target -> None
        assert achievement(None, 100, "higher_better", MANAGEMENT_POLICY).value is None
        assert achievement(80, None, "higher_better", MANAGEMENT_POLICY).value is None


class TestFunctionPolicy:
    """Tests for FUNCTION_POLICY adhering to the specified rules."""

    def test_function_policy_rules(self):
        # 1. higher_better: actual/target capped 0..1
        res = achievement(80, 100, "higher_better", FUNCTION_POLICY)
        assert res.value == 0.8
        assert res.state == "measured"

        res_over = achievement(120, 100, "higher_better", FUNCTION_POLICY)
        assert res_over.value == 1.0
        assert res_over.state == "measured"

        # 2. lower_better: target/actual capped 0..1
        res_lo = achievement(120, 100, "lower_better", FUNCTION_POLICY)
        assert pytest.approx(res_lo.value, rel=1e-5) == 0.8333333333333334
        assert res_lo.state == "measured"

        res_lo_over = achievement(50, 100, "lower_better", FUNCTION_POLICY)
        assert res_lo_over.value == 1.0
        assert res_lo_over.state == "measured"

        # 3. actual missing -> excluded (counts against coverage), state missing_actual
        res_miss_act = achievement(None, 100, "higher_better", FUNCTION_POLICY)
        assert res_miss_act.value is None
        assert res_miss_act.state == "missing_actual"

        # 4. target missing or <=0 -> invalid_target, excluded
        res_miss_tgt = achievement(80, None, "higher_better", FUNCTION_POLICY)
        assert res_miss_tgt.value is None
        assert res_miss_tgt.state == "invalid_target"

        res_zero_tgt = achievement(80, 0, "higher_better", FUNCTION_POLICY)
        assert res_zero_tgt.value is None
        assert res_zero_tgt.state == "invalid_target"

        res_neg_tgt = achievement(80, -10, "higher_better", FUNCTION_POLICY)
        assert res_neg_tgt.value is None
        assert res_neg_tgt.state == "invalid_target"

        # 5. actual==0 & lower_better -> 1.0
        res_zero_lo = achievement(0, 100, "lower_better", FUNCTION_POLICY)
        assert res_zero_lo.value == 1.0
        assert res_zero_lo.state == "measured"

        # 6. actual==0 & higher_better -> 0.0
        res_zero_hi = achievement(0, 100, "higher_better", FUNCTION_POLICY)
        assert res_zero_hi.value == 0.0
        assert res_zero_hi.state == "measured"

        # 7. negative actual -> 0.0 flagged (state negative_actual)
        res_neg_hi = achievement(-10, 100, "higher_better", FUNCTION_POLICY)
        assert res_neg_hi.value == 0.0
        assert res_neg_hi.state == "negative_actual"

        res_neg_lo = achievement(-10, 100, "lower_better", FUNCTION_POLICY)
        assert res_neg_lo.value == 0.0
        assert res_neg_lo.state == "negative_actual"

        # 8. unknown direction -> unknown_direction, None
        res_unk = achievement(80, 100, "random", FUNCTION_POLICY)
        assert res_unk.value is None
        assert res_unk.state == "unknown_direction"


class TestPureFunctions:
    """Tests for contribution, score, status, grade, and validate_weights."""

    def test_contribution(self):
        assert contribution(0.8, 0.5) == 0.4
        assert contribution(1.0, 0.3) == 0.3
        assert contribution(None, 0.5) is None

    def test_score_all_measured(self):
        kpis = [
            KPIResult(achievement=0.8, weight=0.5, contribution=0.4),
            KPIResult(achievement=1.0, weight=0.5, contribution=0.5),
        ]
        res = score(kpis)
        assert res.score == 90.0
        assert res.earned == 0.9
        assert res.measured_weight == 1.0
        assert res.configured_weight == 1.0
        assert res.coverage == 1.0
        assert res.state == "measured"

    def test_score_provisional_when_some_kpis_missing(self):
        # 3 KPIs: weight 0.4, 0.3, 0.3. The 3rd KPI has None achievement.
        kpis = [
            {"achievement": 0.8, "weight": 0.4, "contribution": 0.32},
            {"achievement": 1.0, "weight": 0.3, "contribution": 0.30},
            {"achievement": None, "weight": 0.3, "contribution": None},
        ]
        res = score(kpis)
        # earned = 0.32 + 0.30 = 0.62
        # measured_weight = 0.4 + 0.3 = 0.7
        # score = earned / measured_weight * 100 = 0.62 / 0.7 * 100 = 88.5714
        assert pytest.approx(res.score, rel=1e-4) == 88.5714
        assert pytest.approx(res.earned, rel=1e-4) == 0.62
        assert pytest.approx(res.measured_weight, rel=1e-4) == 0.7
        assert pytest.approx(res.configured_weight, rel=1e-4) == 1.0
        assert pytest.approx(res.coverage, rel=1e-4) == 0.7
        assert res.state == "provisional"

    def test_score_no_data(self):
        kpis = [
            KPIResult(achievement=None, weight=0.5),
            KPIResult(achievement=None, weight=0.5),
        ]
        res = score(kpis)
        assert res.score is None
        assert res.earned is None
        assert res.measured_weight == 0.0
        assert res.configured_weight == 1.0
        assert res.coverage == 0.0
        assert res.state == "no_data"

        empty_res = score([])
        assert empty_res.score is None
        assert empty_res.state == "no_data"

    def test_status_bands(self):
        assert status(95.0) == "On Track"
        assert status(85.0) == "On Track"
        assert status(84.99) == "Attention"
        assert status(75.0) == "Attention"
        assert status(74.99) == "At Risk"
        assert status(50.0) == "At Risk"
        assert status(0.0) == "At Risk"
        assert status(None) == "No data"

    def test_grade_thresholds(self):
        # Default thresholds: A>=95, B>=90, C>=80, D>=70, E<70
        assert grade(96.0) == "A"
        assert grade(95.0) == "A"
        assert grade(94.9) == "B"
        assert grade(90.0) == "B"
        assert grade(89.9) == "C"
        assert grade(80.0) == "C"
        assert grade(79.9) == "D"
        assert grade(70.0) == "D"
        assert grade(69.9) == "E"
        assert grade(0.0) == "E"
        assert grade(None) is None

        # Custom thresholds
        custom_th = {"A": 90, "B": 80, "C": 70, "D": 60}
        assert grade(90.0, custom_th) == "A"
        assert grade(85.0, custom_th) == "B"
        assert grade(75.0, custom_th) == "C"
        assert grade(65.0, custom_th) == "D"
        assert grade(55.0, custom_th) == "E"

    def test_validate_weights(self):
        # Exactly 1.0
        validate_weights([0.5, 0.3, 0.2])
        validate_weights({"kpi1": 0.7, "kpi2": 0.3})

        # Within tolerance (±0.001)
        validate_weights([0.3333, 0.3333, 0.3334])  # sum = 1.0
        validate_weights([0.5, 0.5005])  # sum = 1.0005 (diff 0.0005 <= 0.001)

        # Outside tolerance
        with pytest.raises(ValueError, match=r"KPI weights must sum to 1\.0"):
            validate_weights([0.5, 0.4])  # sum = 0.9

        with pytest.raises(ValueError, match=r"KPI weights must sum to 1\.0"):
            validate_weights([0.5, 0.502])  # sum = 1.002 (diff 0.002 > 0.001)
