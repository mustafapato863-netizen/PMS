"""Pre-Approvals IP Offshore importer: per-row method, errors, warnings, stored result (synthetic data only)."""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from Data_Cleaning_Teams.preapprovals_offshore import (
    DISAGREEMENT_CODE,
    SHEET_NAME,
    TARGET_CODE,
    process_preapprovals_offshore,
)
from config.database import Base
from models.models import KPIValue, PerformanceRecord, Team
from services.preapprovals_offshore_scoring import NEW_METHOD_ID, OffshoreCounts, score_counts

COUNT_COLUMNS = (
    "AssignedRequest",
    "ApprovedRequests",
    "RejectedRequests",
    "PolicyRej",
    "ApprovalWithin48HR",
    "SubmittedClaims",
    "ErrosClaims",
)


def _row(employee_id, *, date=None, month=None, precomputed=False, **counts):
    values = {"AssignedRequest": 100, "ApprovedRequests": 90, "RejectedRequests": 5, "PolicyRej": 2,
              "ApprovalWithin48HR": 85, "SubmittedClaims": 200, "ErrosClaims": 2}
    values.update(counts)
    row = {
        "HRID": employee_id,
        "AgentName": f"Test Agent {employee_id}",
        "Date": date,
        "Month": month,
        **values,
    }
    if precomputed:
        row.update({
            "RejectionRate": 0.40,
            "InitialError%": 0.50,
            "%ofSubmissionWithinDuedate": 0.60,
            "T.Rejection%": 0.03,
            "T.InitialError%": 0.03,
            "T.Submission%": 0.90,
        })
    return row


def _totals_row(rows):
    totals = {"HRID": None, "AgentName": "Total", "Date": None, "Month": None}
    for column in COUNT_COLUMNS:
        totals[column] = sum(float(row.get(column) or 0) for row in rows if row.get("AgentName") != "Total")
    return totals


def _workbook(rows, *, drop=()):
    frame = pd.DataFrame(rows)
    frame = frame.drop(columns=list(drop), errors="ignore")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=SHEET_NAME, index=False)
    buffer.seek(0)
    return buffer


def _expected_score(**overrides):
    base = dict(assigned=100, approved=90, rejected=5, policy_rejected=2, approved_within_48h=85, submitted=200, errors=2)
    base.update(overrides)
    return score_counts(OffshoreCounts(
        assigned=float(base["assigned"]),
        approved=float(base["approved"]),
        rejected=float(base["rejected"]),
        policy_rejected=float(base["policy_rejected"]),
        approved_within_48h=float(base["approved_within_48h"]),
        submitted=float(base["submitted"]),
        errors=float(base["errors"]),
    ))


def test_june_row_is_scored_from_raw_counts_and_totals_row_is_ignored():
    rows = [_row("TA-OF-001", date=datetime(2026, 6, 1))]
    rows.append(_totals_row(rows))
    df = process_preapprovals_offshore(_workbook(rows))

    expected = _expected_score()
    assert df.iloc[0]["Performance"] == pytest.approx(expected.score / 100, abs=1e-6)
    assert df.iloc[0]["ScoringMethod"] == NEW_METHOD_ID
    assert df.iloc[0]["ControllableRejections"] == pytest.approx(3.0)
    assert df.iloc[0]["ControllableRejectionRate"] == pytest.approx(0.03)
    assert df.iloc[0]["PolicyRejectionRate"] == pytest.approx(0.02)
    assert df.iloc[0]["PolicyShareOfRejections"] == pytest.approx(0.4)
    assert df.iloc[1]["AgentName"] == "Total"
    assert df.iloc[1]["ScoringMethod"] is None or pd.isna(df.iloc[1]["ScoringMethod"])


def test_may_row_keeps_the_legacy_formula_and_has_no_new_keys():
    # Legacy: 0.5*0.40 + 0.2*0.50 + 0.3*0.60 = 0.48 (claims > 0).
    rows = [_row("TA-OF-002", date=datetime(2026, 5, 1), precomputed=True)]
    df = process_preapprovals_offshore(_workbook(rows, drop=()))

    assert df.iloc[0]["Performance"] == pytest.approx(0.48, abs=1e-6)
    assert "ScoringMethod" not in df.columns  # no June 2026 row: no derived columns at all
    assert "ControllableRejections" not in df.columns


def test_boundary_on_one_sheet_scores_each_row_by_its_own_period():
    rows = [
        _row("TA-OF-003", date=datetime(2026, 5, 1), precomputed=True),
        _row("TA-OF-004", date=datetime(2026, 6, 1), precomputed=True),
    ]
    df = process_preapprovals_offshore(_workbook(rows))

    assert df.iloc[0]["Performance"] == pytest.approx(0.48, abs=1e-6)  # May: legacy
    assert df.iloc[1]["Performance"] == pytest.approx(_expected_score().score / 100, abs=1e-6)  # June: new
    assert pd.isna(df.iloc[0]["ScoringMethod"]) or df.iloc[0]["ScoringMethod"] is None
    assert df.iloc[1]["ScoringMethod"] == NEW_METHOD_ID


def test_wrong_precomputed_columns_still_give_the_right_score_and_only_warn():
    rows = [_row("TA-OF-005", date=datetime(2026, 6, 1), precomputed=True)]
    df = process_preapprovals_offshore(_workbook(rows))

    assert df.iloc[0]["Performance"] == pytest.approx(_expected_score().score / 100, abs=1e-6)
    notices = df.attrs.get("column_warnings") or []
    codes = {(item["code"], tuple(item["headers"])) for item in notices}
    assert (DISAGREEMENT_CODE, ("RejectionRate",)) in codes
    assert (DISAGREEMENT_CODE, ("InitialError%",)) in codes
    assert (DISAGREEMENT_CODE, ("%ofSubmissionWithinDuedate",)) in codes
    assert (TARGET_CODE, ("T.Rejection%",)) in codes
    assert all(item["sheet"] == SHEET_NAME for item in notices)


def test_precomputed_columns_that_agree_produce_no_warning():
    # Achievement the new method computes: rejection 0.01/0.03, error 1, submission 1.
    row = _row("TA-OF-006", date=datetime(2026, 6, 1), precomputed=True)
    expected = _expected_score()
    row.update({
        "RejectionRate": expected.achievements["Rejection"],
        "InitialError%": 1.0,
        "%ofSubmissionWithinDuedate": 1.0,
        "T.Rejection%": 0.01,
        "T.InitialError%": 0.01,
        "T.Submission%": 0.90,
    })
    df = process_preapprovals_offshore(_workbook([row]))

    ours = [item for item in (df.attrs.get("column_warnings") or [])
            if item["code"] in (DISAGREEMENT_CODE, TARGET_CODE)]
    assert ours == []


def test_missing_required_raw_column_is_a_clear_error_naming_the_column():
    rows = [_row("TA-OF-007", date=datetime(2026, 6, 1))]
    with pytest.raises(ValueError, match="PolicyRej"):
        process_preapprovals_offshore(_workbook(rows, drop=("PolicyRej",)))


def test_missing_raw_column_is_not_needed_when_the_sheet_has_only_earlier_periods():
    rows = [_row("TA-OF-008", date=datetime(2026, 5, 1), precomputed=True)]
    df = process_preapprovals_offshore(_workbook(rows, drop=("PolicyRej",)))

    assert df.iloc[0]["Performance"] == pytest.approx(0.48, abs=1e-6)


def test_blank_count_in_a_june_row_is_a_row_error_naming_the_column():
    rows = [_row("TA-OF-009", date=datetime(2026, 6, 1), AssignedRequest=None)]
    with pytest.raises(ValueError, match="data row 1.*AssignedRequest"):
        process_preapprovals_offshore(_workbook(rows))


def test_row_whose_period_cannot_be_determined_is_an_import_error_for_that_row():
    rows = [_row("TA-OF-010", date=None, month="Sometime")]
    with pytest.raises(ValueError, match="data row 1: reporting period cannot be determined"):
        process_preapprovals_offshore(_workbook(rows))


def test_month_column_with_year_is_used_when_date_is_missing():
    rows = [_row("TA-OF-011", date=None, month="June 2026")]
    df = process_preapprovals_offshore(_workbook(rows))

    assert df.iloc[0]["ScoringMethod"] == NEW_METHOD_ID


def test_end_to_end_upload_stores_score_grade_kpi_values_and_payload():
    from services.seeding_service import DatabaseSeeder

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        rows = [
            _row("TA-OF-020", date=datetime(2026, 6, 1)),
            _row("TA-OF-021", date=datetime(2026, 5, 1), precomputed=True),
        ]
        DatabaseSeeder().process_uploaded_file("PMS_Synthetic.xlsx", _workbook(rows).getvalue(), db_session=session)

        records = (
            session.query(PerformanceRecord)
            .join(Team, Team.id == PerformanceRecord.team_id)
            .filter(Team.name == "Pre-Approvals IP Offshore")
            .all()
        )
        by_month = {record.month: record for record in records}
        june, may = by_month["June"], by_month["May"]

        expected = _expected_score()
        assert float(june.score) == pytest.approx(expected.score)
        assert june.grade == expected.grade
        june_kpis = {row.kpi_key: row for row in session.query(KPIValue).filter(KPIValue.record_id == june.id).all()}
        assert set(june_kpis) == {"Rejection", "InitialError", "Submission", "PolicyRejection"}
        assert float(june_kpis["Rejection"].target_value) == pytest.approx(0.01)
        assert float(june_kpis["Submission"].target_value) == pytest.approx(0.90)
        assert float(june_kpis["PolicyRejection"].weight_applied) == 0.0
        assert float(june_kpis["PolicyRejection"].contribution) == 0.0
        payload_raw = june.record_payload["raw_data"]
        assert payload_raw["ScoringMethod"] == NEW_METHOD_ID
        assert payload_raw["ControllableRejections"] == pytest.approx(3.0)
        assert float(payload_raw["PolicyRej"]) == 2.0  # existing raw key kept as stored

        may_kpis = {row.kpi_key for row in session.query(KPIValue).filter(KPIValue.record_id == may.id).all()}
        assert "PolicyRejection" not in may_kpis
        assert (may.record_payload or {}).get("raw_data", {}).get("ScoringMethod") is None
    finally:
        session.close()
        engine.dispose()


def test_role_column_is_kept_when_the_sheet_has_one():
    from processors.excel_processor import ExcelProcessor

    rows = [dict(_row("TA-OF-012", date=datetime(2026, 6, 1)), Role="Employee")]
    excel_file = pd.ExcelFile(_workbook(rows))
    frame = ExcelProcessor().process_sheet_preapprovals(excel_file)

    assert frame.iloc[0]["Role"] == "Employee"
    assert frame.iloc[0]["ScoringMethod"] == NEW_METHOD_ID


def test_team_dashboard_actuals_follow_the_method_marker():
    from api.dependencies import serialize_performance_record
    from models.schemas import EvaluationData, PerformanceRecord as SchemaRecord

    counts = {
        "AssignedRequest": "100", "ApprovedRequests": "90", "RejectedRequests": "8", "PolicyRej": "4",
        "ApprovalWithin48HR": "85", "SubmittedClaims": "200", "ErrosClaims": "2",
    }

    def record(raw):
        return SchemaRecord(
            id="TA-OF-901_2026_June", employee_id="TA-OF-901", employee_name="Test Agent",
            team="Pre-Approvals IP Offshore", month="June", year=2026,
            evaluation=EvaluationData(score=62.5, grade="E"), raw_data=raw,
        )

    marked = serialize_performance_record(record({**counts, "ScoringMethod": NEW_METHOD_ID}))
    earlier = serialize_performance_record(record(dict(counts)))

    # June 2026 rows: controllable (8 - 4) / 100. Earlier rows: all rejections, 8 / 100.
    assert marked["actual"]["rejection_rate"] == pytest.approx(0.04)
    assert earlier["actual"]["rejection_rate"] == pytest.approx(0.08)
    assert marked["actual"]["submission_rate"] == pytest.approx(earlier["actual"]["submission_rate"])
