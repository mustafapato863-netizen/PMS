"""Tests for What-If simulator and scoring rules explainer."""

import pytest

from services.ai.what_if_service import (
    KpiInput,
    WhatIfResult,
    compute_achievement,
    compute_weighted_score,
    simulate_kpi_improvement,
    simulate_kpi_improvement_dict,
)
from services.ai.scoring_rules_explainer import ScoreRulesExplainer


def test_compute_achievement_higher_better():
    assert compute_achievement(90, 100, "higher_better") == 0.9
    assert compute_achievement(120, 100, "higher_better") == 1.0  # capped
    assert compute_achievement(50, 100, "higher_better") == 0.5


def test_compute_achievement_lower_better():
    assert compute_achievement(10, 5, "lower_better") == 0.5  # target/actual
    assert compute_achievement(2, 5, "lower_better") == 1.0  # capped
    assert compute_achievement(0, 5, "lower_better") == 1.0  # divide-by-zero safe


def test_compute_weighted_score():
    kpis = [
        KpiInput("Booking", 90, 100, 0.5, "higher_better"),  # 0.45
        KpiInput("Rejection", 10, 5, 0.5, "lower_better"),   # 0.5
    ]
    assert compute_weighted_score(kpis) == 70.0


def test_simulate_higher_better_improvement():
    kpis = [KpiInput("Booking", 80, 100, 1.0, "higher_better")]
    result = simulate_kpi_improvement(kpis, "Booking", 10)
    assert result is not None
    assert result.current_score == 80.0
    assert result.projected_score == 90.0
    assert result.score_delta == 10.0
    assert result.current_grade == "C"  # 80 -> C
    assert result.projected_grade == "B"  # 90 -> B
    assert result.capped is False


def test_simulate_lower_better_improvement():
    kpis = [KpiInput("Rejection", 10, 5, 1.0, "lower_better")]
    result = simulate_kpi_improvement(kpis, "Rejection", 5)
    assert result is not None
    # actual 10 -> 5, achievement target/actual = 5/5 = 1.0
    assert result.projected_score == 100.0
    assert result.projected_achievement == 1.0
    assert result.capped is True


def test_simulate_cap_respected():
    kpis = [KpiInput("Booking", 95, 100, 1.0, "higher_better")]
    result = simulate_kpi_improvement(kpis, "Booking", 20)  # would be 115
    assert result is not None
    assert result.projected_score == 100.0  # capped
    assert result.capped is True


def test_simulate_unknown_kpi():
    kpis = [KpiInput("Booking", 80, 100, 1.0, "higher_better")]
    assert simulate_kpi_improvement(kpis, "Unknown", 5) is None


def test_simulate_dict_wrapper():
    kpis = [{"name": "Booking", "actual": 80, "target": 100, "weight": 1.0, "direction": "higher_better"}]
    result = simulate_kpi_improvement_dict(kpis, "Booking", 10)
    assert result is not None
    assert result["projected_score"] == 90.0


def test_explainer_canonical_sources():
    explainer = ScoreRulesExplainer()
    result = explainer.explain(passport=None)
    assert result["grade_thresholds"]["A"] == 95.0
    assert result["grade_thresholds"]["D"] == 70.0
    assert result["achievement_cap"] == 1.0
    assert "higher_better" in result["formula"]
    assert result["weights"] == []


def test_explainer_to_xml_bounded():
    explainer = ScoreRulesExplainer()
    xml = explainer.to_xml(passport=None)
    assert "<AUTHORIZED_SCORING_RULES>" in xml
    assert len(xml) < 600
