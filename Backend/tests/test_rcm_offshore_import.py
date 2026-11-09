"""Vertical RCM Offshore import: view weights, positions, and the legacy-sheet skip."""

import pandas as pd

from config.loader import find_team_config_by_db_name, load_team_config
from repositories.performance_repository import _team_filter_values
from services.marketing_import_service import (
    MarketingImportService,
    RcmOffshoreImportService,
    legacy_offshore_sheet_enabled,
    load_rcm_offshore_team_configs,
)
from services.scoring_basis_comparison import compare_scoring_basis
from services.seeding_service import json_safe
from services.summary_records_service import SummaryFilters, matches
from utils.report_scope import _exact_team_keys, filter_records_by_scope, user_can_access_team
from utils.team_identity import dedupe_egypt_resubmission_records, is_egypt_resubmission_team


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


def test_egypt_resubmission_aliases_use_same_config_and_calculation_while_uae_remains_separate():
    configs = load_rcm_offshore_team_configs()
    assert configs["resubmission"]["team"] == "Resubmission"
    assert configs["re-submission egy"]["team"] == "Resubmission"

    egy_primary = load_team_config("Resubmission")
    egy_alias = load_team_config("Re-Submission EGY")
    uae_config = load_team_config("Re-Submission")
    assert egy_primary["region"] == "EGY"
    assert egy_alias["region"] == "EGY"
    assert egy_primary["team"] == egy_alias["team"] == "Resubmission"
    assert find_team_config_by_db_name("Re-Submission EGY") == egy_alias
    assert uae_config["region"] == "UAE"
    assert uae_config["team"] == "Re-Submission"
    assert [k["key"] for k in uae_config["kpis"]] == [
        "quality_errors_rate",
        "rejection_rate_after_resubmission",
        "tat",
    ]

    parsed = RcmOffshoreImportService().parse_frame(pd.DataFrame(
        _month("Resubmission", "Resubmission Analyst", "SGHD70104", [
            ("Quality Errors Rate", 0.5, "Internal Process", "Lower Better", 0.05, 0.07),
            ("Rejection Rate After Re-Submission", 0, "Customer", "Lower Better", 0.6, 0),
            ("TAT", 0.5, "Customer", "Higher Better", 1, 0.84),
        ])
        + _month("Re-Submission EGY", "Resubmission Analyst", "SGHD70105", [
            ("Quality Errors Rate", 0.5, "Internal Process", "Lower Better", 0.05, 0.07),
            ("Rejection Rate After Re-Submission", 0, "Customer", "Lower Better", 0.6, 0),
            ("TAT", 0.5, "Customer", "Higher Better", 1, 0.84),
        ])
    ))
    assert parsed.report["rejected_employee_months"] == []
    by_id = {record.employee_id: record for record in parsed.records}
    # Stored source names are preserved while calculation is identical
    assert by_id["SGHD70104"].team == "Resubmission"
    assert by_id["SGHD70105"].team == "Re-Submission EGY"
    assert by_id["SGHD70104"].evaluation.score == by_id["SGHD70105"].evaluation.score
    assert by_id["SGHD70104"].evaluation.grade == by_id["SGHD70105"].evaluation.grade
    assert [k["kpi_key"] for k in by_id["SGHD70104"].kpi_values] == [
        "egy_resubmission_quality_errors",
        "egy_resubmission_rejection",
        "egy_resubmission_tat",
    ]
    assert [k["kpi_key"] for k in by_id["SGHD70105"].kpi_values] == [
        "egy_resubmission_quality_errors",
        "egy_resubmission_rejection",
        "egy_resubmission_tat",
    ]


def test_dedupe_and_authorization_for_egypt_resubmission_aliases_and_uae():
    assert is_egypt_resubmission_team("Resubmission") is True
    assert is_egypt_resubmission_team("Re-Submission EGY") is True
    assert is_egypt_resubmission_team("Re-Submission") is False

    rows = [
        {"employee_id": "SGHD70104", "team": "Resubmission", "region": "EGY", "year": 2026, "month": "September", "performance_level": "Employee", "branches": []},
        {"employee_id": "SGHD70104", "team": "Re-Submission EGY", "region": "EGY", "year": 2026, "month": "September", "performance_level": "Employee", "branches": []},
        {"employee_id": "SGHD70105", "team": "Re-Submission EGY", "region": "EGY", "year": 2026, "month": "September", "performance_level": "Employee", "branches": []},
        {"employee_id": "UAE9001", "team": "Re-Submission", "region": "UAE", "year": 2026, "month": "September", "performance_level": "Employee", "branches": []},
    ]
    deduped = dedupe_egypt_resubmission_records(rows)
    assert len(deduped) == 3
    assert [(r["employee_id"], r["team"]) for r in deduped] == [
        ("SGHD70104", "Resubmission"),
        ("SGHD70105", "Re-Submission EGY"),
        ("UAE9001", "Re-Submission"),
    ]

    assert _exact_team_keys("Resubmission") == {"resubmission", "re-submission egy"}
    assert _exact_team_keys("Re-Submission EGY") == {"resubmission", "re-submission egy"}
    assert _exact_team_keys("Re-Submission") == {"re-submission"}
    assert _team_filter_values("Resubmission") == ("resubmission", "re-submission egy")
    assert _team_filter_values("Re-Submission EGY") == ("resubmission", "re-submission egy")
    assert _team_filter_values("Re-Submission") == ("re-submission",)

    # Authorized Egypt RCM scope includes both Egypt aliases (deduplicated) and excludes UAE
    egy_scope = {"role": "Manager", "accessible_teams": ["Resubmission"]}
    assert user_can_access_team(egy_scope, "Resubmission") is True
    assert user_can_access_team(egy_scope, "Re-Submission EGY") is True
    assert user_can_access_team(egy_scope, "Re-Submission") is False

    egy_authorized = dedupe_egypt_resubmission_records(filter_records_by_scope(rows, egy_scope))
    assert [(r["employee_id"], r["team"]) for r in egy_authorized] == [
        ("SGHD70104", "Resubmission"),
        ("SGHD70105", "Re-Submission EGY"),
    ]
    egy_filters = SummaryFilters(team="Resubmission", region="EGY")
    assert matches(rows[1], egy_filters) is True
    assert matches(rows[3], egy_filters) is False

    # Scoring basis comparison treats both Egypt aliases as the same team scope across months
    aug = [{
        "employee_id": "SGHD70104",
        "team": "Re-Submission EGY",
        "position": "Resubmission Analyst",
        "performance_level": "Employee",
        "kpi_values": [{
            "kpi_key": "egy_resubmission_quality_errors",
            "target_value": 0.08,
            "weight_applied": 0.4,
            "direction": "lower_better",
            "unit": "%",
            "actual_value": 0.07,
            "evaluation_pinned": True,
        }],
    }]
    sep = [{
        "employee_id": "SGHD70104",
        "team": "Resubmission",
        "position": "Resubmission Analyst",
        "performance_level": "Employee",
        "kpi_values": [{
            "kpi_key": "egy_resubmission_quality_errors",
            "target_value": 0.05,
            "weight_applied": 0.5,
            "direction": "lower_better",
            "unit": "%",
            "actual_value": 0.07,
            "evaluation_pinned": True,
        }],
    }]
    comparison = compare_scoring_basis(sep, aug)
    assert comparison["state"] == "changed"
    assert set(comparison["reasons"]) == {"target", "weight"}
