"""Marketing aggregation weight is the stored target, not the scoring weight."""
from __future__ import annotations

import json
from pathlib import Path

from config.loader import load_team_config, resolve_team_config
from services.kpi_aggregation import aggregate_kpi_metric
from services.marketing_import_service import MarketingImportService


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "evaluation_baseline"


def test_weighted_average_uses_target_values_and_ignores_scoring_weight():
    fixture = json.loads((FIXTURES / "marketing_aggregate_rows.json").read_text(encoding="utf-8"))
    metric = aggregate_kpi_metric(fixture["rows"], fixture["definition"])
    changed_weight = dict(fixture["definition"])
    changed_weight["weight"] = 0.80
    same_metric = aggregate_kpi_metric(fixture["rows"], changed_weight)

    assert metric.actual == 35.0
    assert metric.target == 25.0
    assert same_metric == metric
    assert fixture["definition"]["weight"] == 0.10
    assert fixture["definition"]["aggregation"]["weight_col"] == "Target Value"


def test_generic_resolver_returns_the_default_account_manager_set():
    config = load_team_config("Marketing")
    resolved = resolve_team_config(config, "Employee", "Account Manager")
    assert [kpi["key"] for kpi in resolved["kpis"]] == [
        "am_campaign_delivery",
        "am_campaign_delivery_ontime",
        "am_deficit",
        "am_requests",
        "am_modifications",
        "am_edit_rate",
        "am_projects_ontime",
    ]
    assert "period_variants" in resolved


def test_marketing_importer_selects_the_may_2026_variant_only_when_labels_match():
    position = load_team_config("Marketing")["performance_levels"]["Employee"]["positions"]["Account Manager"]
    variant = position["period_variants"][0]
    default_rows = [{"row": index, "kpi_label": kpi["label"]} for index, kpi in enumerate(position["kpis"], start=1)]
    variant_rows = [{"row": index, "kpi_label": kpi["label"]} for index, kpi in enumerate(variant["kpis"], start=1)]

    default_name, default_kpis, _matched = MarketingImportService._select_kpi_set(
        position, default_rows, period_date="2026-04-01"
    )
    august_name, august_kpis, _matched = MarketingImportService._select_kpi_set(
        position, variant_rows, period_date="2026-08-01"
    )

    assert default_name == "default"
    assert [kpi["key"] for kpi in default_kpis] == [kpi["key"] for kpi in position["kpis"]]
    assert august_name == "may_2026_onward"
    assert [kpi["key"] for kpi in august_kpis] == ["am_requests", "am_edit_rate", "am_projects_ontime"]
    assert variant["effective_from"] == "2026-05-01"
