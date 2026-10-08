"""Characterize current historical reads.

The target-ratio rewrite below is observed current behavior. It is not the
pinned-history contract required by later phases.
"""
from __future__ import annotations

import pytest

from models.models import KPIValue, ManagementKPIConfig, ManagementKPISnapshot, PerformanceRecord
from services.dashboard_record_service import _normalise_kpi_values


def _queries_row() -> dict:
    return {
        "kpi_key": "Queries",
        "label": "Queries Handled",
        "actual_value": 0.60,
        "target_value": 0.55,
        "achievement_ratio": 1.0,
        "weight_applied": 0.30,
        "contribution": 0.30,
        "direction": None,
        "month": "July",
    }


def test_target_ratio_read_rewrites_persisted_achievement_from_current_direction():
    persisted = _queries_row()
    current_definition = {
        "key": "Queries",
        "label": "Queries Handled",
        "direction": "lower_better",
        "score_formula": "target_ratio",
    }
    rewritten = _normalise_kpi_values(
        [persisted],
        {"kpis": [current_definition]},
        {"Queries": current_definition},
        "CSR",
        {"Queries": "higher_better"},
    )[0]

    assert persisted["achievement_ratio"] == 1.0
    assert rewritten["direction"] == "lower_better"
    assert rewritten["direction_source"] == "config"
    assert rewritten["direction_corrected"] is True
    assert rewritten["achievement_ratio"] == pytest.approx(0.55 / 0.60)
    assert rewritten["contribution"] == pytest.approx((0.55 / 0.60) * 0.30)
    assert rewritten["month"] == "July"


def test_same_persisted_values_are_rewritten_identically_for_july_and_august_labels():
    definition = {"key": "Queries", "direction": "lower_better", "score_formula": "target_ratio"}
    july = _queries_row()
    august = _queries_row()
    august["month"] = "August"
    july_result = _normalise_kpi_values([july], {"kpis": [definition]}, {"Queries": definition}, "CSR", {"Queries": "higher_better"})[0]
    august_result = _normalise_kpi_values([august], {"kpis": [definition]}, {"Queries": definition}, "CSR", {"Queries": "higher_better"})[0]

    assert july_result["achievement_ratio"] == august_result["achievement_ratio"]
    assert july_result["contribution"] == august_result["contribution"]


def test_baseline_80_read_keeps_persisted_achievement_but_still_replaces_direction():
    definition = {
        "key": "combined_acceptance_rate",
        "label": "Acceptance Rate",
        "direction": "higher_better",
        "score_formula": "baseline_80",
    }
    row = {
        "kpi_key": "combined_acceptance_rate",
        "actual_value": 0.90,
        "target_value": 0.95,
        "achievement_ratio": 0.42,
        "weight_applied": 0.50,
        "contribution": 0.21,
        "direction": None,
    }
    result = _normalise_kpi_values(
        [row],
        {"kpis": [definition]},
        {"combined_acceptance_rate": definition},
        "Pre-Approvals IP Final Dubai",
        {"combined_acceptance_rate": "higher_better"},
    )[0]

    assert result["achievement_ratio"] == 0.42
    assert result["contribution"] == 0.21
    assert result["direction"] == "higher_better"
    assert result["direction_source"] == "config"
    assert "direction_corrected" not in result


def test_orm_persists_score_inputs_and_management_period_fields():
    """Positive persistence shape only.

    Absence of configuration_version_id and KPI direction is an audit fact.
    Phase 1 is expected to map those fields, so this test must not forbid them.
    """
    assert {"actual_value", "target_value", "achievement_ratio", "weight_applied", "contribution"} <= set(
        KPIValue.__table__.columns.keys()
    )
    assert "target_value" in ManagementKPIConfig.__table__.columns
    assert "effective_month" in ManagementKPIConfig.__table__.columns
    assert "effective_year" in ManagementKPIConfig.__table__.columns
    assert "actual_value" in ManagementKPISnapshot.__table__.columns
    assert {"month", "year"} <= set(ManagementKPISnapshot.__table__.columns.keys())
    assert list(PerformanceRecord.__table__.primary_key.columns.keys()) == ["id", "year"]
