"""Unmapped-column notices list only headers that no importer step reads.

Synthetic header rows only. Each team's names are read by its importer, the shared
cleaner or the seeder; the classifier must not list them. Names no step reads stay
listed, and workbook layout (side KPI table, pandas duplicates) is never listed.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from services.upload_header_notices import (
    LAYOUT_COLUMNS,
    MAX_HEADERS_PER_NOTICE,
    ORDINARY_OUTBOUND_HEADERS,
    SHARED_READ_COLUMNS,
    _READ_MODULES,
    classify_raw_headers,
)

BACKEND = Path(__file__).resolve().parents[1]
LAYOUT_ROW = [
    "Updated Pre-Approvals IP KPI Table",
    "KPI",
    "Weight",
    "Target",
    "Direction",
    "Achievement Score Formula",
    "Weighted Score",
    "Score Range",
    "Classification",
    "Distribution",
    "Date.1",
]


def _unmapped(sheet: str, headers: list[str]) -> list[str]:
    notices = classify_raw_headers(sheet, headers)
    listed: list[str] = []
    for notice in notices:
        if notice["code"] == "unmapped_columns":
            listed.extend(notice["headers"])
    return listed


# Names each team's importer reads by name (the same sets the importers declare).
READ_NAMES = {
    "Inbound": ["Dubai_Booking", "Sharjah_Booking", "Ajman_Booking", "Clinics_Booking", "Dubai_Attend", "Sharjah_Attend", "Ajman_Attend", "Clinics_Attend", "UTZ%Ach%", "AHT"],
    "Sales": ["A.OPCensus", "T.OPCensus", "A.OPRevenue", "T.OPRevenue", "A.IPCensus", "T.IPCensus", "A.IPRevenue", "T.IPRevenue", "OPCensusAch%", "OPRevenueAch%", "IPCensusAch%", "IPRevenueAch%", "A.Visits", "T.Visits", "A.CBDTour", "T.CBDTour", "A.ClinicActivity", "T.ClinicActivity", "A.CorporateActivity", "T.CorporateActivity"],
    "Pharmacy": ["Prescription Ach%", "NoofPrescriptionAch%", "Noof Prescription Ach%"],
    "Submission": ["RejectedClaimsAmount3MonthPrevious", "RAClaimsAmount(3MonthPrevious)"],
    "Re-Submission": ["AllocatedClaims", "QualitySamples", "FinalErrorsClaims", "TotalSubmittedWithinTAT", "RemittanceAmount", "RejectedClaimsPrevious3Months", "G", "J"],
    "Pre-Approvals IP Offshore": ["RejectedRequests", "PolicyRej", "AssignedRequest", "ApprovedRequests", "ApprovalWithin48HR", "SubmittedClaims", "ErrosClaims", "RejectionRate", "InitialError%", "%ofSubmissionWithinDuedate"],
    "Pre-Approvals OP Dubai": ["A.InitialRejectionRate", "T.InitialRejection", "SubmittedWithinDay", "TotalNumberOfCallsperDay", "AssignedRequest", "RejectedRequests", "T.%AbandonedCalls", "TotalAbandonedCallsPerDay", "SubmittedRequests", "SubmittedWithinHour", "TotalAttendedCallsPerDay", "T.SubmissionWithinHour%", "T.%ofAttendedCalls"],
    "Pre-Approvals OP Final SHJAJM": ["SubmittedRequests", "ManualRequest", "SubmittedWithinHour", "RejectedRequests", "T.InitialRejection", "T.SubmissionWithinHour%"],
    "Pre-Approvals IP Final SHJAJM": ["AssignedRequest", "ApprovedRequests", "SubmittedWithinMonth(Untill3rdofnextmonth)", "T.AcceptanceRate", "T.SubmissionWithinMonth%"],
    "Pre-Approvals IP Final Dubai": ["AssignedRequest", "ApprovedRequests", "SubmittedWithinMonth(Untill3rdofnextmonth)", "DischargeRequests", "DischargeWithinHour", "A.AcceptanceRate", "A.SubmissionWithinMonth%", "A.Discharge%Within1Hour"],
    "Pre-Approvals IP Elective Dubai": ["AssignedRequests", "ApprovedRequests", "RejectedRequests", "ApprovalWithin48HR", "ApprovalWithin1.5HR", "ApprovalWithin48HR/1.5HR", "T.InitialRejection%", "T.%OfApprovalwithin48HR/1.5HR"],
}

# Names no importer step reads: they stay listed under the existing wording.
UNREAD_NAMES = {
    "Inbound": ["Calls Offered"],
    "Sales": ["A.Total Census", "T.Total Census", "A.Total Revenue", "T.Total Revenue", "SalesActivitiesAch%", "Performance_Score"],
    "Coding": ["Quality Errors Rate Ach%", "Rejection Rate Ach%", "TAT Ach%"],
    "CSR": ["CSR Rejection %", "CSR Queries %", "Attended C.R %"],
    "Pharmacy": ["Pharmacy Notes"],
    "Pre-Approvals IP Offshore": ["T.IP Initial Rejection %", "T.Error %", "T.% of Approval within 48 hrs"],
    "Pre-Approvals OP Dubai": ["A.Initial Rejection Rate Ach%"],
}


@pytest.mark.parametrize("sheet", sorted(READ_NAMES))
def test_names_the_importer_reads_are_not_listed(sheet):
    assert _unmapped(sheet, READ_NAMES[sheet]) == []


@pytest.mark.parametrize("sheet", sorted(UNREAD_NAMES))
def test_names_no_step_reads_are_still_listed(sheet):
    assert _unmapped(sheet, UNREAD_NAMES[sheet]) == UNREAD_NAMES[sheet]


def test_layout_artefacts_are_never_listed_on_any_team_sheet():
    for sheet in ("Sales", "Coding", "Pre-Approvals OP Final SHJAJM"):
        assert _unmapped(sheet, ["Date", *LAYOUT_ROW]) == []
    assert "Date.1" not in _unmapped("CSR", ["Date", "Date.1"])


def test_layout_names_are_the_documented_side_table_headings():
    assert set(LAYOUT_COLUMNS) == {
        "KPI",
        "Weight",
        "Target",
        "Direction",
        "Achievement Score Formula",
        "Weighted Score",
        "Score Range",
        "Classification",
        "Distribution",
    }


def test_duplicate_suffix_is_layout_only_when_the_base_header_exists():
    assert _unmapped("Coding", ["Date", "Date.1"]) == []
    assert _unmapped("Coding", ["Notes.1"]) == ["Notes.1"]


def test_whitespace_and_case_variants_of_read_names_are_not_listed():
    assert _unmapped("Pre-Approvals IP Offshore", ["rejected requests", "POLICY REJ", "Assigned Request"]) == []


def test_positional_run_after_an_anchor_is_read_and_the_next_column_is_not():
    headers = ["Dubai_Booking", "Trend Two", "Trend Three", "Trend Four", "Trend Five"]
    assert _unmapped("Inbound", headers) == ["Trend Five"]


def test_positional_run_stops_at_the_grade_column():
    headers = ["Dubai_Attend", "Trend Two", "Performance Grade", "Trend After Grade"]
    assert _unmapped("Inbound", headers) == ["Trend After Grade"]


def test_sales_activity_pattern_reads_activity_columns_and_not_their_ach_spellings():
    assert _unmapped("Sales", ["A.Visits", "Visits Ach%"]) == ["Visits Ach%"]


def test_pharmacy_prescription_achievement_is_read_by_name_fragment():
    assert _unmapped("Pharmacy", ["Prescription Ach%", "Pharmacy Notes"]) == ["Pharmacy Notes"]


def test_limits_hold_for_a_non_outbound_sheet():
    headers = [f"Extra {index:02d}" for index in range(1, 31)]
    notices = classify_raw_headers("Sales", headers)
    unmapped = next(item for item in notices if item["code"] == "unmapped_columns")
    assert len(unmapped["headers"]) == MAX_HEADERS_PER_NOTICE
    assert unmapped["truncated"] is True


def test_outbound_template_behaviour_is_unchanged():
    notices = classify_raw_headers(
        "Outbound",
        [*ORDINARY_OUTBOUND_HEADERS, "Date.1", "KPI", "Mystery Column"],
    )
    unmapped = next(item for item in notices if item["code"] == "unmapped_columns")
    assert unmapped["headers"] == ["Date.1", "KPI", "Mystery Column"]


def _source(module_name: str) -> str:
    return Path(importlib.import_module(module_name).__file__).read_text(encoding="utf-8")


# Importers that take some declared names from a shared scoring module.
_EXTRA_SOURCES = {
    "Data_Cleaning_Teams.preapprovals_offshore": ("services.preapprovals_offshore_scoring",),
}


def test_declared_names_still_appear_in_their_importer_source():
    """Drift guard: a declared read name must still be written in the importer."""
    for sheet, module_name in _READ_MODULES.items():
        module = importlib.import_module(module_name)
        text = _source(module_name)
        for extra in _EXTRA_SOURCES.get(module_name, ()):
            text += _source(extra)
        for name in getattr(module, "READ_COLUMNS", ()):
            assert name in text, f"{sheet}: {name!r} is declared but not in {module_name}"
        for name, _count in getattr(module, "READ_ANCHORS", ()):
            assert name in text, f"{sheet}: anchor {name!r} is declared but not in {module_name}"
        for pattern in getattr(module, "READ_PATTERNS", ()):
            loose = text.casefold().replace(" ", "").replace("_", "").replace(".", "")
            assert pattern in loose, f"{sheet}: pattern {pattern!r} is declared but not in {module_name}"


def test_shared_read_names_still_appear_in_the_cleaner_or_seeder():
    text = (BACKEND / "cleaned.py").read_text(encoding="utf-8") + (
        BACKEND / "services" / "seeding_service.py"
    ).read_text(encoding="utf-8")
    for name in SHARED_READ_COLUMNS:
        assert name in text, f"{name!r} is listed as shared-read but no longer in cleaned.py or the seeder"
