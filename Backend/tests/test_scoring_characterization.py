import json
import os
import pytest
from services.kpi_service import KPIService
from services.kpi_aggregation import capped_achievement, AggregatedKpiMetric
from services.management_bsc_service import _direction_ratio
from repositories.json_repos import JSONKPIWeightsRepository, JSONTargetsRepository


@pytest.fixture
def kpi_service():
    weights_repo = JSONKPIWeightsRepository()
    targets_repo = JSONTargetsRepository()
    return KPIService(weights_repo, targets_repo)


class TestScoringCharacterization:
    """Pins the exact CURRENT output of all three implementations before any refactoring."""

    # 1. Normal performance
    def test_normal_performance(self, kpi_service):
        # higher_better: actual=80, target=100
        assert kpi_service._calculate_achievement(80, 100, is_inverse=False) == 80.0
        assert capped_achievement(AggregatedKpiMetric(actual=80, target=100), "higher_better") == 0.8
        assert _direction_ratio("higher_better", 80, 100) == 0.8

        # lower_better: actual=80, target=100 (target/actual = 1.25, capped at 100%/1.0 in kpi_service and aggregation, uncapped in bsc)
        assert kpi_service._calculate_achievement(80, 100, is_inverse=True) == 100.0
        assert capped_achievement(AggregatedKpiMetric(actual=80, target=100), "lower_better") == 1.0
        assert _direction_ratio("lower_better", 80, 100) == 1.25

    # 2. Over-achievement
    def test_over_achievement(self, kpi_service):
        # higher_better: actual=120, target=100
        assert kpi_service._calculate_achievement(120, 100, is_inverse=False) == 100.0
        assert capped_achievement(AggregatedKpiMetric(actual=120, target=100), "higher_better") == 1.0
        assert _direction_ratio("higher_better", 120, 100) == 1.2

        # lower_better: actual=50, target=100
        assert kpi_service._calculate_achievement(50, 100, is_inverse=True) == 100.0
        assert capped_achievement(AggregatedKpiMetric(actual=50, target=100), "lower_better") == 1.0
        assert _direction_ratio("lower_better", 50, 100) == 2.0

        # lower_better: actual=120, target=100 (under-achievement for lower_better: 100/120 = 83.33%)
        assert pytest.approx(kpi_service._calculate_achievement(120, 100, is_inverse=True), rel=1e-5) == 83.33333333333334
        assert pytest.approx(capped_achievement(AggregatedKpiMetric(actual=120, target=100), "lower_better"), rel=1e-5) == 0.8333333333333334
        assert pytest.approx(_direction_ratio("lower_better", 120, 100), rel=1e-5) == 0.8333333333333334

    # 3. actual = 0
    def test_actual_zero(self, kpi_service):
        # higher_better: actual=0, target=100
        assert kpi_service._calculate_achievement(0, 100, is_inverse=False) == 0.0
        assert capped_achievement(AggregatedKpiMetric(actual=0, target=100), "higher_better") == 0.0
        assert _direction_ratio("higher_better", 0, 100) == 0.0

        # lower_better: actual=0, target=100
        # kpi_service: zero_actual_value = 100.0
        assert kpi_service._calculate_achievement(0, 100, is_inverse=True) == 100.0
        # aggregation: actual <= 0 -> 1.0
        assert capped_achievement(AggregatedKpiMetric(actual=0, target=100), "lower_better") == 1.0
        # management_bsc: actual==0 and target!=0 -> None
        assert _direction_ratio("lower_better", 0, 100) is None

    # 4. target = 0
    def test_target_zero(self, kpi_service):
        # higher_better: actual=80, target=0
        assert kpi_service._calculate_achievement(80, 0, is_inverse=False) == 0.0
        assert capped_achievement(AggregatedKpiMetric(actual=80, target=0), "higher_better") is None
        assert _direction_ratio("higher_better", 80, 0) is None

        # lower_better: actual=80, target=0
        assert kpi_service._calculate_achievement(80, 0, is_inverse=True) == 0.0
        assert capped_achievement(AggregatedKpiMetric(actual=80, target=0), "lower_better") is None
        assert _direction_ratio("lower_better", 80, 0) == 0.0

    # 5. actual = 0 and target = 0
    def test_actual_zero_and_target_zero(self, kpi_service):
        # higher_better: actual=0, target=0
        assert kpi_service._calculate_achievement(0, 0, is_inverse=False) == 0.0
        assert capped_achievement(AggregatedKpiMetric(actual=0, target=0), "higher_better") is None
        assert _direction_ratio("higher_better", 0, 0) == 1.0

        # lower_better: actual=0, target=0
        assert kpi_service._calculate_achievement(0, 0, is_inverse=True) == 100.0
        assert capped_achievement(AggregatedKpiMetric(actual=0, target=0), "lower_better") is None
        assert _direction_ratio("lower_better", 0, 0) == 1.0

    # 6. Negative actual
    def test_negative_actual(self, kpi_service):
        # higher_better: actual=-10, target=100
        assert kpi_service._calculate_achievement(-10, 100, is_inverse=False) == 0.0
        assert capped_achievement(AggregatedKpiMetric(actual=-10, target=100), "higher_better") == 0.0
        assert _direction_ratio("higher_better", -10, 100) == -0.1

        # lower_better: actual=-10, target=100
        # kpi_service: min(max(-1000, 0), 100) -> 0.0
        assert kpi_service._calculate_achievement(-10, 100, is_inverse=True) == 0.0
        # aggregation: actual <= 0 -> 1.0 (legacy behavior!)
        assert capped_achievement(AggregatedKpiMetric(actual=-10, target=100), "lower_better") == 1.0
        # management_bsc: target / actual = 100 / -10 = -10.0
        assert _direction_ratio("lower_better", -10, 100) == -10.0

    # 7. None / missing actual
    def test_none_actual(self, kpi_service):
        # higher_better: actual=None, target=100
        # kpi_service safe_float(None) -> 0.0
        assert kpi_service._calculate_achievement(None, 100, is_inverse=False) == 0.0
        assert capped_achievement(AggregatedKpiMetric(actual=None, target=100), "higher_better") is None
        assert _direction_ratio("higher_better", None, 100) is None

        # lower_better: actual=None, target=100
        # kpi_service safe_float(None) -> 0.0 -> actual==0 -> zero_actual_value (100.0)
        assert kpi_service._calculate_achievement(None, 100, is_inverse=True) == 100.0
        assert capped_achievement(AggregatedKpiMetric(actual=None, target=100), "lower_better") is None
        assert _direction_ratio("lower_better", None, 100) is None

    # 8. None target
    def test_none_target(self, kpi_service):
        # higher_better: actual=80, target=None
        assert kpi_service._calculate_achievement(80, None, is_inverse=False) == 0.0
        assert capped_achievement(AggregatedKpiMetric(actual=80, target=None), "higher_better") is None
        assert _direction_ratio("higher_better", 80, None) is None

        # lower_better: actual=80, target=None
        assert kpi_service._calculate_achievement(80, None, is_inverse=True) == 0.0
        assert capped_achievement(AggregatedKpiMetric(actual=80, target=None), "lower_better") is None
        assert _direction_ratio("lower_better", 80, None) is None

    # 9. Precomputed achievement column handling (kpi_service row evaluation)
    def test_kpi_service_precomputed_achievement(self, kpi_service):
        data_path = os.path.join(os.path.dirname(__file__), "..", "data", "performance_records.json")
        with open(data_path, "r", encoding="utf-8") as f:
            all_records = json.load(f)
        base_row = dict(next(r for r in all_records if r.get("team") == "Inbound")["raw_data"])

        # Test row evaluation with precomputed achievement column present
        row = dict(base_row)
        row["A.Attend%"] = "80%"
        row["T.Attend%"] = "75%"
        row["Attend%Ach%"] = "104.4%"  # precomputed column
        score, grade, kpi_vals = kpi_service.calculate_performance_multi_team("Inbound", row)
        attend_kpi = next(kv for kv in kpi_vals if kv["kpi_key"] == "Attendance")
        # Precomputed achievement column is scaled and capped at 1.0 (GLOBAL_KPI_ACHIEVEMENT_CAP)
        assert attend_kpi["achievement_ratio"] == 1.0

        # When target is 0.0 and precomputed column like {kpi_key}Ach% exists
        row_zero_target = dict(base_row)
        row_zero_target["A.Attend%"] = "80%"
        row_zero_target["T.Attend%"] = "0%"
        row_zero_target["Attend%Ach%"] = "95%"
        score_zt, grade_zt, kpi_vals_zt = kpi_service.calculate_performance_multi_team("Inbound", row_zero_target)
        attend_kpi_zt = next(kv for kv in kpi_vals_zt if kv["kpi_key"] == "Attendance")
        assert attend_kpi_zt["achievement_ratio"] == 0.95

        # When target is 0.0 and no precomputed column exists -> 0.0
        row_zero_target_no_ach = dict(base_row)
        row_zero_target_no_ach["A.Attend%"] = "80%"
        row_zero_target_no_ach["T.Attend%"] = "0%"
        # Remove any attend achievement keys
        for k in list(row_zero_target_no_ach.keys()):
            if "attend" in k.lower() and "ach" in k.lower():
                del row_zero_target_no_ach[k]
        score_no, grade_no, kpi_vals_no = kpi_service.calculate_performance_multi_team("Inbound", row_zero_target_no_ach)
        attend_kpi_no = next(kv for kv in kpi_vals_no if kv["kpi_key"] == "Attendance")
        assert attend_kpi_no["achievement_ratio"] == 0.0


class TestRegressionSnapshot:
    """Verifies that employee scores for a real month match the snapshot fixture exactly."""

    def test_january_regression_snapshot(self, kpi_service):
        fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "regression_january_snapshot.json")
        data_path = os.path.join(os.path.dirname(__file__), "..", "data", "performance_records.json")

        assert os.path.exists(fixture_path), f"Fixture not found: {fixture_path}"
        with open(fixture_path, "r", encoding="utf-8") as f:
            expected_records = json.load(f)

        with open(data_path, "r", encoding="utf-8") as f:
            all_records = json.load(f)

        records_by_id = {r["id"]: r for r in all_records if r.get("month") == "January"}

        assert len(expected_records) == 156

        for expected in expected_records:
            rec_id = expected["id"]
            assert rec_id in records_by_id, f"Record {rec_id} not found in performance_records.json"
            actual_rec = records_by_id[rec_id]
            team = actual_rec["team"]
            row = actual_rec.get("raw_data", {})

            score, grade, kpi_vals = kpi_service.calculate_performance_multi_team(
                team, row, performance_level=actual_rec.get("performance_level", "Employee")
            )

            assert round(score, 4) == expected["score"], f"Score mismatch for {rec_id}: {score} vs {expected['score']}"
            assert grade == expected["grade"], f"Grade mismatch for {rec_id}: {grade} vs {expected['grade']}"
            assert len(kpi_vals) == len(expected["kpi_values"]), f"KPI count mismatch for {rec_id}"

            for actual_kv, expected_kv in zip(kpi_vals, expected["kpi_values"]):
                assert actual_kv["kpi_key"] == expected_kv["kpi_key"]
                assert actual_kv["achievement_ratio"] == expected_kv["achievement_ratio"], (
                    f"Achievement ratio mismatch for {rec_id} {actual_kv['kpi_key']}: "
                    f"{actual_kv['achievement_ratio']} vs {expected_kv['achievement_ratio']}"
                )
                assert actual_kv["contribution"] == expected_kv["contribution"], (
                    f"Contribution mismatch for {rec_id} {actual_kv['kpi_key']}: "
                    f"{actual_kv['contribution']} vs {expected_kv['contribution']}"
                )
