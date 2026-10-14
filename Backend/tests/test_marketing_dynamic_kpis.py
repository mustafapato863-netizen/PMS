"""The Marketing sheet defines each employee-month's KPI set.

Synthetic rows only. Labels, weights and units follow the September 2026 shape in the
acceptance workbook, but no employee names come from it.
"""

import pandas as pd
import pytest

from services.marketing_import_service import (
    MarketingImportService,
    _generated_kpi_key,
)


def _kpi(label, weight, direction, unit, perspective, target, actual):
    return {
        "label": label,
        "weight": weight,
        "direction": direction,
        "unit": unit,
        "perspective": perspective,
        "target": target,
        "actual": actual,
    }


# Media Buyer, September 2026 shape: App installs removed, Reporting added, CPL weight 0.2.
MEDIA_BUYER_SEPTEMBER = [
    _kpi("CPL", 0.2, "Lower Better", "AED", "Financial", 100.0, 80.0),
    _kpi("CR", 0.1, "Higher Better", "%", "Internal Process", 0.3, 0.3),
    _kpi("Leads", 0.4, "Higher Better", "count", "Customer", 100.0, 50.0),
    _kpi("CPV", 0.1, "Lower Better", "AED", "Financial", 100.0, 100.0),
    _kpi("Revenue", 0.1, "Higher Better", "AED", "Financial", 1000.0, 500.0),
    _kpi("Reporting", 0.1, "Higher Better", "%", "Internal Process", 1.0, 1.0),
]

# Media Buyer, May 2026 shape: App installs present, CPL weight 0.1, no Reporting.
MEDIA_BUYER_MAY = [
    _kpi("CPL", 0.1, "Lower Better", "AED", "Financial", 100.0, 80.0),
    _kpi("CR", 0.3, "Higher Better", "%", "Internal Process", 0.3, 0.3),
    _kpi("Leads", 0.3, "Higher Better", "count", "Customer", 100.0, 50.0),
    _kpi("CPV", 0.1, "Lower Better", "AED", "Financial", 100.0, 100.0),
    _kpi("Revenue", 0.1, "Higher Better", "AED", "Financial", 1000.0, 500.0),
    _kpi("# App installs", 0.1, "Higher Better", "count", "Customer", 1000.0, 1000.0),
]


def _rows(employee_id: str, month: str, position: str, kpis: list[dict], performance_score=None) -> list[dict]:
    return [
        {
            "Employee ID": employee_id,
            "Region": "EGY",
            "Team": "Marketing",
            "Employee Name": f"Synthetic {employee_id}",
            "Position": position,
            "Performance Level": "Employee",
            "Date": pd.Timestamp(month),
            "Perspective": kpi["perspective"],
            "KPI": kpi["label"],
            "Direction": kpi["direction"],
            "Weight": kpi["weight"],
            "Target Value": kpi["target"],
            "Target Unit": kpi["unit"],
            "Actual Value": kpi["actual"],
            "Actual Unit": kpi["unit"],
            "Achievement %": None,
            "Weighted Score %": None,
            "Performance Score": performance_score,
        }
        for kpi in kpis
    ]


def _frame(*rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([row for group in rows for row in group])


def _record(result, month: str):
    return next(record for record in result.records if record.month == month)


def _kpi_by_label(record) -> dict[str, dict]:
    return {value["label"]: value for value in record.kpi_values}


def test_generated_key_is_deterministic_for_a_new_label():
    assert _generated_kpi_key("Media Buyer", "Reporting") == "mkt_media_buyer_reporting"
    assert _generated_kpi_key("Media Buyer", "Reporting") == _generated_kpi_key("Media Buyer", "Reporting")


def test_new_kpi_label_imports_with_a_generated_key_and_its_row_weight():
    frame = _frame(_rows("SYN001", "2026-09-01", "Media Buyer", MEDIA_BUYER_SEPTEMBER, 0.75))

    result = MarketingImportService().parse_frame(frame)

    reporting = _kpi_by_label(_record(result, "September"))["Reporting"]
    assert reporting["kpi_key"] == "mkt_media_buyer_reporting"
    assert reporting["weight_applied"] == pytest.approx(0.1)
    assert reporting["unit"] == "%"
    assert reporting["direction"] == "higher_better"


def test_september_case_imports_and_configured_labels_keep_their_keys():
    social = [
        _kpi("Response Time", 0.3, "Lower Better", "min", "Internal Process", 10.0, 8.0),
        _kpi("Response rate (%)", 0.3, "Higher Better", "%", "Customer", 0.9, 0.9),
        _kpi("Channels growth rate", 0.2, "Higher Better", "%", "Customer", 0.1, 0.1),
        _kpi("Content calendar adherence", 0.1, "Higher Better", "%", "Internal Process", 0.9, 0.45),
        _kpi("Reporting", 0.1, "Higher Better", "%", "Internal Process", 1.0, 1.0),
    ]
    frame = _frame(
        _rows("SYN002", "2026-09-01", "Media Buyer", MEDIA_BUYER_SEPTEMBER, 0.75),
        _rows("SYN003", "2026-09-01", "Social Media Specialist", social),
    )

    result = MarketingImportService().parse_frame(frame)

    assert len(result.records) == 2
    social_record = next(record for record in result.records if record.position == "Social Media Specialist")
    keys = {value["label"]: value["kpi_key"] for value in social_record.kpi_values}
    assert keys["Response rate (%)"] == "sms_response_rate"
    assert keys["Content calendar adherence"] == "mkt_social_media_specialist_content_calendar_adherence"
    assert keys["Reporting"] == "mkt_social_media_specialist_reporting"


def test_changed_weights_in_one_month_leave_earlier_months_unchanged():
    alone = MarketingImportService().parse_frame(_frame(_rows("SYN004", "2026-05-01", "Media Buyer", MEDIA_BUYER_MAY, 0.75)))
    together = MarketingImportService().parse_frame(_frame(
        _rows("SYN004", "2026-05-01", "Media Buyer", MEDIA_BUYER_MAY, 0.75),
        _rows("SYN004", "2026-09-01", "Media Buyer", MEDIA_BUYER_SEPTEMBER, 0.75),
    ))

    may_alone = _record(alone, "May")
    may_together = _record(together, "May")
    september = _record(together, "September")
    assert may_together.kpi_values == may_alone.kpi_values
    assert _kpi_by_label(may_together)["CPL"]["weight_applied"] == pytest.approx(0.1)
    assert _kpi_by_label(september)["CPL"]["weight_applied"] == pytest.approx(0.2)


def test_a_removed_kpi_does_not_appear_for_that_month():
    result = MarketingImportService().parse_frame(_frame(
        _rows("SYN005", "2026-05-01", "Media Buyer", MEDIA_BUYER_MAY, 0.75),
        _rows("SYN005", "2026-09-01", "Media Buyer", MEDIA_BUYER_SEPTEMBER, 0.75),
    ))

    assert "mb_app_installs" in {value["kpi_key"] for value in _record(result, "May").kpi_values}
    assert "mb_app_installs" not in {value["kpi_key"] for value in _record(result, "September").kpi_values}


# Old: this raised MarketingImportValidationError for the whole upload.
# New: the employee-month is rejected, its row is named, and the other months still import.
def test_an_employee_month_missing_a_kpi_row_is_rejected_with_a_row_numbered_weight_error():
    # CPL (0.2) is absent, so the weights sum to 0.8.
    incomplete = [kpi for kpi in MEDIA_BUYER_SEPTEMBER if kpi["label"] != "CPL"]
    frame = _frame(_rows("SYN006", "2026-09-01", "Media Buyer", incomplete, 0.75))

    result = MarketingImportService().parse_frame(frame)

    assert result.records == []
    rejected = result.report["rejected_employee_months"]
    assert len(rejected) == 1
    weight_errors = [reason for reason in rejected[0]["reasons"] if reason["code"] == "WEIGHT_SUM"]
    assert len(weight_errors) == 1
    assert weight_errors[0]["row"] == 2
    assert "0.800" in weight_errors[0]["message"]
    assert any(
        warning["code"] == "EMPLOYEE_MONTH_REJECTED" and warning["row"] == 2
        for warning in result.report["warnings"]
    )


# Old: "Sideways" on any KPI raised INVALID_DIRECTION for the whole upload.
# New: on a configured KPI the configured direction wins and the row is a warning.
def test_a_bad_direction_on_a_configured_kpi_is_a_warning_and_the_configured_direction_wins():
    kpis = [dict(kpi) for kpi in MEDIA_BUYER_SEPTEMBER]
    frame = _frame(_rows("SYN007", "2026-09-01", "Media Buyer", kpis, 0.75))
    frame.loc[2, "Direction"] = "Sideways"  # Excel row 4: Leads, configured higher_better

    result = MarketingImportService().parse_frame(frame)

    assert len(result.records) == 1
    assert result.report["rejected_employee_months"] == []
    warnings = [warning for warning in result.report["warnings"] if warning["code"] == "DIRECTION_MISMATCH"]
    assert len(warnings) == 1
    assert warnings[0]["row"] == 4
    assert "Leads" in warnings[0]["message"]
    assert "SYN007" in warnings[0]["message"]
    assert "September 2026" in warnings[0]["message"]
    leads = _kpi_by_label(_record(result, "September"))["Leads"]
    assert leads["direction"] == "higher_better"


# Old: "Sideways" on a KPI not in config raised INVALID_DIRECTION for the whole upload.
# New: the row's direction is the only one, so a bad value rejects its employee-month.
def test_a_bad_direction_on_a_new_kpi_rejects_that_employee_month():
    kpis = [dict(kpi) for kpi in MEDIA_BUYER_SEPTEMBER]
    frame = _frame(_rows("SYN007", "2026-09-01", "Media Buyer", kpis, 0.75))
    frame.loc[5, "Direction"] = "Sideways"  # Excel row 7: Reporting, not in the Media Buyer config

    result = MarketingImportService().parse_frame(frame)

    assert result.records == []
    reasons = result.report["rejected_employee_months"][0]["reasons"]
    assert [(reason["row"], reason["code"]) for reason in reasons] == [(7, "INVALID_DIRECTION")]


# Old: a non-numeric Target Value raised INVALID_NUMBER for the whole upload.
# New: the employee-month is rejected, and the row number is in the report.
def test_a_non_numeric_value_rejects_that_employee_month():
    kpis = [dict(kpi) for kpi in MEDIA_BUYER_SEPTEMBER]
    frame = _frame(_rows("SYN007", "2026-09-01", "Media Buyer", kpis, 0.75))
    frame["Target Value"] = frame["Target Value"].astype(object)
    frame.loc[2, "Target Value"] = "not a number"  # Excel row 4

    result = MarketingImportService().parse_frame(frame)

    assert result.records == []
    reasons = result.report["rejected_employee_months"][0]["reasons"]
    assert [(reason["row"], reason["code"]) for reason in reasons] == [(4, "INVALID_NUMBER")]


# Old: a duplicate KPI raised MarketingImportValidationError for the whole upload.
# New: the employee-month is rejected, and the duplicate's row is named in the report.
def test_a_duplicate_kpi_in_one_employee_month_rejects_that_employee_month():
    rows = _rows("SYN008", "2026-09-01", "Media Buyer", MEDIA_BUYER_SEPTEMBER, 0.75)
    frame = _frame(rows, [rows[1]])

    result = MarketingImportService().parse_frame(frame)

    assert result.records == []
    reasons = result.report["rejected_employee_months"][0]["reasons"]
    duplicates = [reason for reason in reasons if reason["code"] == "DUPLICATE_KPI"]
    assert duplicates and duplicates[0]["row"] == 2 + len(rows)


def test_an_alias_keeps_the_existing_key_and_the_configured_label():
    web = [
        _kpi("Page load speed", 0.25, "Lower Better", "sec", "Internal Process", 2.0, 1.5),
        _kpi("Website uptime (%)", 0.25, "Higher Better", "%", "Internal Process", 0.99, 0.99),
        _kpi("Error / bug resolution rate", 0.25, "Higher Better", "%", "Internal Process", 0.9, 0.9),
        _kpi("Request delivery timeliness", 0.25, "Higher Better", "%", "Internal Process", 0.9, 0.9),
    ]

    result = MarketingImportService().parse_frame(_frame(_rows("SYN009", "2026-07-01", "Web Developer", web, 1.0)))

    speed = next(value for value in _record(result, "July").kpi_values if value["kpi_key"] == "wd_page_speed")
    assert speed["label"] == "Page load time"


def test_engine_score_that_differs_from_the_sheet_is_a_warning_not_an_error():
    frame = _frame(_rows("SYN010", "2026-09-01", "Media Buyer", MEDIA_BUYER_SEPTEMBER, 0.2))

    result = MarketingImportService().parse_frame(frame)

    record = _record(result, "September")
    assert record.evaluation.score == pytest.approx(75.0)
    warnings = [warning for warning in result.report["warnings"] if warning["column"] == "Performance Score"]
    assert len(warnings) == 1
    assert warnings[0]["employee_id"] == "SYN010"
    assert warnings[0]["month"] == "September"
    assert warnings[0]["uploaded"] == pytest.approx(20.0)
    assert warnings[0]["calculated"] == pytest.approx(75.0)
