"""Basis changes are labeled as evaluation settings, not employee movement."""
from services import reporting_evidence_service as module
from services.reporting_evidence_service import ReportingEvidenceService
from tests.test_reporting_evidence_service import config, make_record, value


def test_basis_change_is_annotated_on_its_own_month(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    records = [
        make_record("A", "July", 82.85, kpis=[value(actual=46.07, target=65, contribution=0.7, weight=0.7)]),
        make_record("A", "August", 79.93, kpis=[value(actual=46.07, target=70, contribution=0.329, weight=0.5)]),
    ]
    movement = ReportingEvidenceService().movement(records[1:], records[:1], (2026, 8))
    trend = ReportingEvidenceService().trend(records, (2026, 8))

    assert movement["configuration_version_effect"] == -2.92
    assert movement["kpi_contribution_movements"] == []
    assert movement["scoring_basis_changed"] is True
    assert movement["raw_performance_changed"] is False
    assert movement["kpi_basis_comparisons"] == [{
        "key": "Quality",
        "actual_changed": False,
        "basis_changed": True,
        "previous_actual": 46.07,
        "current_actual": 46.07,
        "previous_target": 65.0,
        "current_target": 70.0,
        "previous_weight": 70.0,
        "current_weight": 50.0,
    }]
    assert "Evaluation settings changed" in movement["narrative"]
    assert "declined" not in movement["narrative"].casefold()
    assert [point["value"] for point in trend["series"]] == [82.85, 79.93]
    assert trend["series"][0]["basis_changed"] is False
    assert trend["series"][1]["basis_changed"] is True
    assert trend["series"][1]["basis_state"] == "uniform"


def test_raw_actual_change_stays_distinct_from_a_basis_change(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    records = [
        make_record("A", "July", 80, kpis=[value(actual=40, target=65, contribution=0.4, weight=0.7)]),
        make_record("A", "August", 70, kpis=[value(actual=30, target=70, contribution=0.2, weight=0.5)]),
    ]
    movement = ReportingEvidenceService().movement(records[1:], records[:1], (2026, 8))

    assert movement["scoring_basis_changed"] is True
    assert movement["raw_performance_changed"] is True
    assert movement["kpi_basis_comparisons"][0]["actual_changed"] is True
    assert movement["kpi_basis_comparisons"][0]["previous_actual"] == 40
    assert movement["kpi_basis_comparisons"][0]["current_actual"] == 30
    assert "Evaluation settings changed" in movement["narrative"]
    assert "declined" in movement["narrative"].casefold()


def test_zero_net_and_canceling_basis_changes_stay_visible(monkeypatch):
    monkeypatch.setattr(module, "_config", lambda _record: config())
    july = [
        make_record("A", "July", 80, kpis=[value(actual=46.07, target=65, contribution=0.7, weight=0.7)]),
        make_record("B", "July", 80, kpis=[value(actual=46.07, target=65, contribution=0.7, weight=0.7)]),
    ]
    august = [
        make_record("A", "August", 85, kpis=[value(actual=46.07, target=70, contribution=0.5, weight=0.5)]),
        make_record("B", "August", 75, kpis=[value(actual=46.07, target=60, contribution=0.4, weight=0.4)]),
    ]
    movement = ReportingEvidenceService().movement(august, july, (2026, 8))
    trend = ReportingEvidenceService().trend([*july, *august], (2026, 8))

    assert movement["configuration_version_effect"] == 0
    assert movement["scoring_basis_changed"] is True
    assert movement["raw_performance_changed"] is False
    assert movement["kpi_basis_comparisons"][0]["basis_changed"] is True
    assert movement["kpi_basis_comparisons"][0]["actual_changed"] is False
    assert movement["kpi_basis_comparisons"][0]["previous_target"] == 65.0
    assert movement["kpi_basis_comparisons"][0]["current_target"] is None
    assert "Evaluation settings changed" in movement["narrative"]
    assert "unchanged" in movement["narrative"].casefold()
    assert "declined" not in movement["narrative"].casefold()
    assert trend["series"][1]["basis_changed"] is True
    assert trend["series"][1]["basis_state"] == "mixed"
    assert trend["series"][1]["value"] == 80.0
