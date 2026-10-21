"""Vertical RCM Offshore import: view weights, positions, and the legacy-sheet skip."""

import pandas as pd

from config.loader import load_team_config
from services.marketing_import_service import (
    MarketingImportService,
    RcmOffshoreImportService,
    legacy_offshore_sheet_enabled,
    load_rcm_offshore_team_configs,
)
from services.seeding_service import json_safe


def _row(**overrides):
    row = {
        "Employee ID": "SGHD70134",
        "Region": "EGY",
        "Team": "Pre-Approvals IP",
        "Employee Name": "Salma",
        "Position": "Pre-Authorization Specialist",
        "Performance Level": "Employee",
        "Date": pd.Timestamp("2026-09-01"),
        "Perspective": "Internal Process",
        "KPI": "IP Initial Rejection %",
        "Direction": "Lower Better",
        "Weight": 0.3,
        "Target Value": 0.01,
        "Target Unit": "%",
        "Actual Value": 0.02,
    }
    row.update(overrides)
    return row


def _specialist_month(**shared):
    rejection = _row(**shared)
    rejection.update({
        "KPI": "IP Initial Rejection %",
        "Perspective": "Internal Process",
        "Direction": "Lower Better",
        "Weight": 0.3,
    })
    error = _row(**shared)
    error.update({
        "KPI": "Error %",
        "Perspective": "Internal Process",
        "Direction": "Lower Better",
        "Weight": 0.3,
        "Actual Value": 0.0,
    })
    approval = _row(**shared)
    approval.update({
        "KPI": "% Approval within 48 hrs",
        "Perspective": "Customer",
        "Direction": "Higher Better",
        "Weight": 0.4,
        "Target Value": 0.9,
        "Actual Value": 0.95,
    })
    return [rejection, error, approval]


def test_marketing_importer_defaults_stay_on_the_marketing_sheet():
    service = MarketingImportService()
    assert service.sheet_name == "Marketing"
    assert service.enforced_team == "Marketing"
    assert service.allowed_levels == frozenset({"Employee"})
    assert service.preserve_sheet_position is False

    parsed = service.parse_frame(pd.DataFrame([_row(Team="Pre-Approvals IP")]))
    assert parsed.records == []
    assert any(
        issue["code"] == "INVALID_TEAM" and "Employee rows must belong to Marketing" in issue["message"]
        for month in parsed.report["rejected_employee_months"]
        for issue in month["reasons"]
    )


def test_view_weight_is_stored_and_excluded_from_the_weight_sum():
    rows = _specialist_month()
    rows[1]["Weight"] = "view"
    rows[0]["Weight"] = 0.6
    parsed = RcmOffshoreImportService().parse_frame(pd.DataFrame(rows))

    assert len(parsed.records) == 1
    record = parsed.records[0]
    error = next(item for item in record.kpi_values if item["kpi_key"] == "pa_error_rate")
    assert error["view_only"] is True
    assert error["weight_applied"] == 0
    assert error["contribution"] == 0
    scored = [item for item in record.kpi_values if not item.get("view_only")]
    assert abs(sum(item["weight_applied"] for item in scored) - 1) < 0.001


def test_supervisor_keeps_the_managerial_view_kpi_and_senior_keeps_the_sheet_title():
    supervisor = [
        _row(
            **{
                "Employee ID": "SGHD70094",
                "Employee Name": "Hossam Mohamed",
                "Position": "Pre-Authorization Supervisor",
                "Performance Level": "Managerial",
                "KPI": "IP Initial Rejection %",
                "Weight": 0.5,
                "Target Value": 0.01,
                "Actual Value": 0.0,
            }
        ),
        _row(
            **{
                "Employee ID": "SGHD70094",
                "Employee Name": "Hossam Mohamed",
                "Position": "Pre-Authorization Supervisor",
                "Performance Level": "Managerial",
                "KPI": "IP Initial Rejection %(All)",
                "Weight": "View",
                "Target Value": 0.05,
                "Actual Value": 0.03,
            }
        ),
        _row(
            **{
                "Employee ID": "SGHD70094",
                "Employee Name": "Hossam Mohamed",
                "Position": "Pre-Authorization Supervisor",
                "Performance Level": "Managerial",
                "KPI": "Error %",
                "Weight": 0.2,
                "Actual Value": 0.01,
            }
        ),
        _row(
            **{
                "Employee ID": "SGHD70094",
                "Employee Name": "Hossam Mohamed",
                "Position": "Pre-Authorization Supervisor",
                "Performance Level": "Managerial",
                "KPI": "% of Approval within 48 hrs",
                "Perspective": "Customer",
                "Direction": "Higher Better",
                "Weight": 0.3,
                "Target Value": 0.9,
                "Actual Value": 0.96,
            }
        ),
    ]
    senior = _specialist_month(
        **{
            "Employee ID": "SGHD70151",
            "Employee Name": "Senior",
            "Position": "Pre-Authorization Senior Specialist",
        }
    )
    parsed = RcmOffshoreImportService().parse_frame(pd.DataFrame(supervisor + senior))
    by_id = {record.employee_id: record for record in parsed.records}

    hossam = by_id["SGHD70094"]
    assert hossam.performance_level == "Managerial"
    assert hossam.position == "Pre-Authorization Supervisor"
    view = next(item for item in hossam.kpi_values if item["kpi_key"] == "pa_initial_rejection_all")
    assert view["view_only"] is True
    assert view["weight_applied"] == 0
    approval = next(item for item in hossam.kpi_values if item["kpi_key"] == "pa_approval_48h")
    assert approval["label"] == "% Approval within 48 hrs"

    senior_record = by_id["SGHD70151"]
    assert senior_record.position == "Pre-Authorization Senior Specialist"
    assert senior_record.performance_level == "Employee"
    assert {item["kpi_key"] for item in senior_record.kpi_values} == {
        "pa_initial_rejection",
        "pa_error_rate",
        "pa_approval_48h",
    }


def test_a_short_or_duplicate_month_is_still_rejected():
    service = RcmOffshoreImportService()
    short = service.parse_frame(pd.DataFrame([_row()]))
    assert short.records == []
    assert any(reason["code"] == "WEIGHT_SUM" for month in short.report["rejected_employee_months"] for reason in month["reasons"])

    duplicated = _specialist_month()
    duplicated.append(dict(duplicated[0]))
    parsed = service.parse_frame(pd.DataFrame(duplicated))
    assert parsed.records == []
    assert any(reason["code"] == "DUPLICATE_KPI" for month in parsed.report["rejected_employee_months"] for reason in month["reasons"])


def test_json_safe_keeps_a_view_only_flag_as_json_true():
    saved = json_safe({"view_only": True, "weight_applied": 0})
    assert saved["view_only"] is True
    assert saved["weight_applied"] == 0


def _month(team: str, position: str, employee_id: str, rows: list[tuple[str, float, str, str, float, float]]):
    parsed_rows = []
    for label, weight, perspective, direction, target, actual in rows:
        parsed_rows.append(_row(**{
            "Employee ID": employee_id,
            "Employee Name": employee_id,
            "Team": team,
            "Position": position,
            "KPI": label,
            "Weight": weight,
            "Perspective": perspective,
            "Direction": direction,
            "Target Value": target,
            "Actual Value": actual,
        }))
    return parsed_rows


def test_new_egypt_sheet_teams_keep_their_kpis_without_replacing_uae_domains():
    configs = load_rcm_offshore_team_configs()
    assert configs["coding"]["team"] == "Coding EGY"
    assert configs["submission"]["team"] == "Submission EGY"
    assert configs["resubmission"]["team"] == "Resubmission"
    assert load_team_config("Coding")["region"] == "UAE"
    assert load_team_config("Submission")["region"] == "UAE"
    assert "rcm_group" not in load_team_config("Coding")

    parsed = RcmOffshoreImportService().parse_frame(pd.DataFrame(
        _month("Coding", "RCM -SHJ- OP CODING", "SGHD70221", [
            ("Quality Errors Rate", 0.5, "Internal Process", "Lower Better", 0.05, 0.136),
            ("Rejection Rate", 0, "Internal Process", "Lower Better", 0.06, 0),
            ("TAT", 0.5, "Customer", "Higher Better", 0.9, 0.424),
        ])
        + _month("Submission", "Claim & Audit Specialist", "SGHD70133", [
            ("Initial Rejection %", 0.6, "Internal Process", "Lower Better", 0.02, 0.038),
            ("% of Submission Within Due date", 0.4, "Customer", "Higher Better", 0.9, 0.999),
        ])
        + _month("Resubmission", "Resubmission Analyst", "SGHD70104", [
            ("Quality Errors Rate", 0.5, "Internal Process", "Lower Better", 0.05, 0.07),
            ("Rejection Rate After Re-Submission", 0, "Customer", "Lower Better", 0.6, 0),
            ("TAT", 0.5, "Customer", "Higher Better", 1, 0.84),
        ])
    ))
    by_id = {record.employee_id: record for record in parsed.records}
    assert by_id["SGHD70221"].team == "Coding EGY"
    assert by_id["SGHD70133"].team == "Submission EGY"
    assert by_id["SGHD70104"].team == "Resubmission"
    coding_labels = {item["label"] for item in by_id["SGHD70221"].kpi_values}
    assert coding_labels == {"Quality Errors Rate", "Rejection Rate", "TAT"}
    rejection = next(item for item in by_id["SGHD70221"].kpi_values if item["label"] == "Rejection Rate")
    assert rejection["weight_applied"] == 0
    assert parsed.report["rejected_employee_months"] == []


def test_legacy_offshore_sheet_is_skipped_when_rcm_offshore_is_present():
    assert legacy_offshore_sheet_enabled(["RCM Offshore", "Pre-Approvals IP Offshore"]) is False
    assert legacy_offshore_sheet_enabled(["Pre-Approvals IP Offshore"]) is True
    assert legacy_offshore_sheet_enabled(["RCM Offshore"]) is False
