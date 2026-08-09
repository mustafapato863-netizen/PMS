import pytest

from repositories.base import KPIWeightsRepository, TargetsRepository
from services.kpi_service import KPIService


class _WeightsRepo(KPIWeightsRepository):
    def __init__(self):
        self._teams = {}

    def get_by_team(self, team):
        return self._teams.get(team)

    def get_all(self):
        return list(self._teams.values())

    def save(self, record):
        self._teams[record.team] = record
        return record


class _TargetsRepo(TargetsRepository):
    def __init__(self):
        self._teams = {}

    def get_by_team(self, team):
        return self._teams.get(team)

    def get_all(self):
        return list(self._teams.values())

    def save(self, record):
        self._teams[record.team] = record
        return record


def _service():
    return KPIService(_WeightsRepo(), _TargetsRepo())


def test_direct_kpi_above_target_caps_contribution():
    service = _service()

    score, grade, kpis = service.calculate_performance_multi_team(
        "Pharmacy",
        {
            "A.TotalAvgWaitingTime": 100,
            "T.TotalWaitingTime": 100,
            "A.Leakage%": 100,
            "T.Leakage%": 100,
            "A.TenderItemCompliance": 150,
            "T.TenderItemCompliance": 100,
            "A.ATV": 100,
            "T.ATV": 100,
            "NoofPrescriptionAch%": 100,
            "T.NoofPrescriptionsContribution": 100,
        },
    )

    tender = next(k for k in kpis if k["kpi_key"] == "TenderCompliance")
    assert tender["achievement_ratio"] == 1.0
    assert tender["contribution"] == 0.2
    assert score == 100.0
    assert grade == "A"


def test_inverse_kpi_above_target_caps_contribution():
    service = _service()

    score, grade, kpis = service.calculate_performance_multi_team(
        "Pharmacy",
        {
            "A.TotalAvgWaitingTime": 2,
            "T.TotalWaitingTime": 4,
            "A.Leakage%": 100,
            "T.Leakage%": 100,
            "A.TenderItemCompliance": 100,
            "T.TenderItemCompliance": 100,
            "A.ATV": 100,
            "T.ATV": 100,
            "NoofPrescriptionAch%": 100,
            "T.NoofPrescriptionsContribution": 100,
        },
    )

    waiting = next(k for k in kpis if k["kpi_key"] == "WaitingTime")
    assert waiting["achievement_ratio"] == 1.0
    assert waiting["contribution"] == 0.2
    assert score == 100.0
    assert grade == "A"


def test_multiple_kpis_above_100_cap_final_score():
    service = _service()

    score, _, kpis = service.calculate_performance_multi_team(
        "Coding",
        {
            "A.QualityErrors": 1,
            "T.QualityErrors": 1.5,
            "A.Rejection": 1,
            "T.Rejection": 2,
            "A.TAT_Hours": 1,
            "T.TAT_Hours": 4,
        },
    )

    assert score == 100.0
    assert sum(k["contribution"] for k in kpis) == 1.0


def test_mixed_performance_uses_real_achievement_and_capped_contribution():
    service = _service()

    score, _, kpis = service.calculate_performance_multi_team(
        "CSR",
        {
            "A.Rejection": 3.75,
            "T.Rejection": 3,
            "A.Queries": 120,
            "T.Queries": 100,
            "A.AttendedCR": 90,
            "T.AttendedCR": 100,
        },
    )

    contributions = {k["kpi_key"]: k for k in kpis}
    assert contributions["Rejection"]["achievement_ratio"] == 0.8
    assert contributions["Rejection"]["contribution"] == 0.32
    assert contributions["Queries"]["achievement_ratio"] == 1.0
    assert contributions["Queries"]["contribution"] == 0.3
    assert contributions["AttendedCR"]["achievement_ratio"] == 0.9
    assert contributions["AttendedCR"]["contribution"] == 0.27
    assert score == pytest.approx(89.0)


def test_pharmacy_final_score_never_exceeds_100():
    service = _service()

    score, _, kpis = service.calculate_performance_multi_team(
        "Pharmacy",
        {
            "A.TotalAvgWaitingTime": 1,
            "T.TotalWaitingTime": 5,
            "A.Leakage%": 1,
            "T.Leakage%": 2,
            "A.TenderItemCompliance": 200,
            "T.TenderItemCompliance": 100,
            "A.ATV": 300,
            "T.ATV": 100,
            "NoofPrescriptionAch%": 500,
            "T.NoofPrescriptionsContribution": 100,
        },
    )

    assert score == 100.0
    assert all(k["achievement_ratio"] == 1.0 for k in kpis)
    assert all(k["contribution"] <= k["weight_applied"] for k in kpis)
