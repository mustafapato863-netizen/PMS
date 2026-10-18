"""Uploaded Marketing metadata survives canonical reads; SQL numbers stay authoritative."""
import copy
import uuid
from types import SimpleNamespace

import pandas as pd
import pytest

from services.dashboard_record_service import DashboardRecordService
from services.marketing_import_service import MarketingImportService


def source_record():
    specs = [
        ("Response rate (%)", .3, "%", 1., .8727, "Higher Better"),
        ("Channels growth rate", .2, "%", .01, .0125, "Higher Better"),
        ("Response Time", .3, "min", 31., 208., "Lower Better"),
        ("Reporting", .1, "%", 1., .9, "Higher Better"),
        ("Content calendar adherence", .1, "%", 1., .97, "Higher Better"),
    ]
    rows = [{
        "Employee ID": "SYN-META-1", "Employee Name": "Synthetic Only", "Region": "EGY",
        "Team": "Marketing", "Position": "Social Media Specialist", "Performance Level": "Employee",
        "Date": pd.Timestamp("2026-09-01"), "Perspective": "Internal Process", "KPI": label,
        "Direction": direction, "Weight": weight, "Target Value": target, "Target Unit": unit,
        "Actual Value": actual, "Actual Unit": unit, "Achievement %": None,
        "Weighted Score %": None, "Performance Score": None,
    } for label, weight, unit, target, actual, direction in specs]
    return MarketingImportService().parse_frame(pd.DataFrame(rows)).records[0]


def sql_record(source):
    team = SimpleNamespace(name="Marketing", display_name="Marketing", db_name="Marketing", region="EGY")
    employee = SimpleNamespace(employee_id="SYN-META-1", name="Synthetic Only", team=team,
                               position_name="Social Media Specialist", region="EGY")
    values = [SimpleNamespace(**{field: value[field] for field in (
        "kpi_key", "actual_value", "target_value", "achievement_ratio", "weight_applied", "contribution"
    )}) for value in source.kpi_values]
    return SimpleNamespace(id=uuid.uuid4(), year=2026, month="September", team=team, employee=employee,
        performance_level="Employee", position_name="Social Media Specialist", region="EGY", branch_key=None,
        upload_id=None, score=source.evaluation.score, grade=source.evaluation.grade, status="Below",
        record_payload=source.model_dump(mode="json"), kpi_values=values)


@pytest.mark.parametrize("label", ["Reporting", "Content calendar adherence", "Response rate (%)", "Response Time"])
def test_marketing_resolver_preserves_source_metadata_and_score(label):
    source = source_record()
    item = sql_record(source)
    before = copy.deepcopy(item.record_payload)
    original = next(k for k in source.kpi_values if k["label"] == label)
    result = DashboardRecordService(None).resolve_records([item])[0]
    actual = next(k for k in result.kpi_values if k["kpi_key"] == original["kpi_key"])
    assert actual["label"] == original["label"]
    assert actual["unit"] == original["unit"]
    assert actual["perspective"] == original["perspective"]
    assert actual["weight_applied"] == original["weight_applied"]
    assert sum(k["weight_applied"] for k in result.kpi_values) == pytest.approx(1)
    assert result.evaluation.score == pytest.approx(source.evaluation.score)
    assert item.record_payload == before


def test_payload_metadata_never_overrides_relational_numbers():
    item = sql_record(source_record())
    row = next(v for v in item.kpi_values if v.kpi_key.endswith("_reporting"))
    row.actual_value, row.target_value = .5, .8
    row.weight_applied, row.achievement_ratio, row.contribution = .2, .625, .125
    result = DashboardRecordService(None).resolve_records([item])[0]
    actual = next(k for k in result.kpi_values if k["kpi_key"] == row.kpi_key)
    assert actual["label"] == "Reporting"
    assert actual["unit"] == "%"
    for field in ("actual_value", "target_value", "weight_applied", "achievement_ratio", "contribution"):
        assert actual[field] == pytest.approx(getattr(row, field))


def test_malformed_optional_metadata_does_not_break_relational_fallback():
    item = sql_record(source_record())
    key = next(v.kpi_key for v in item.kpi_values if v.kpi_key.endswith("_reporting"))
    item.record_payload = {"kpi_values": [None, "bad", {"kpi_key": key, "label": {}, "unit": []}]}
    result = DashboardRecordService(None).resolve_records([item])[0]
    actual = next(k for k in result.kpi_values if k["kpi_key"] == key)
    assert actual["label"] == key
    assert actual["unit"] == "number"
    assert actual["actual_value"] == pytest.approx(.9)
