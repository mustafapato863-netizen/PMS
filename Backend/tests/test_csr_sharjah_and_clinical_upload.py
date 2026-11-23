import io

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from config.database import Base
from models.models import PerformanceRecord, Team
from services.dashboard_record_service import DashboardRecordService
from services.seeding_service import DatabaseSeeder
from services.csr_sharjah_scoring import score_sharjah_csr, uses_sharjah_csr_score


def test_sharjah_cutover_depends_on_branch_and_reporting_month():
    for team, date, is_new in (
        ("SHJ", "2026-09-30", False),
        ("SHJ", "2026-10-01", True),
        ("Sharjah", "2027-01-31", True),
        ("Dubai", "2026-10-01", False),
        ("AJM", "2026-10-01", False),
    ):
        assert uses_sharjah_csr_score({"Team": team, "Date": date}, "Employee") is is_new


@pytest.mark.parametrize(("serving", "attended", "weights"), [
    (None, None, [0.60, 0.40]),
    (4.0, None, [0.40, 0.25, 0.35]),
    (None, 0.9, [0.40, 0.30, 0.30]),
    (4.0, 0.9, [0.30, 0.20, 0.20, 0.30]),
])
def test_sharjah_missing_optional_values_use_source_weights(serving, attended, weights):
    score, grade, values = score_sharjah_csr({
        "A.CSRRejection%": 0, "T.CSRRejection%": 0.005,
        "A.CSRQueries": 0, "T.QueriesTarget": 0.002,
        "A.CPTConversion%": attended, "T.AttendedC.R": 0.9,
        "ServingTime(min)": serving, "NoofComplaints": 1,
    })
    assert [item["weight_applied"] for item in values[:-1]] == weights
    assert values[-1]["contribution"] == -0.20
    assert (score, grade) == (80.0, "C")


def test_upload_and_dashboard_keep_october_score_and_exclude_unscored_clinical_row():
    csr = pd.DataFrame([{
        "Date": pd.Timestamp("2026-10-01"), "Region": "UAE", "Role": "Emp",
        "HR ID": "SGHS00001", "Agent Name": "Test CSR", "Status": "Active", "Team": "SHJ",
        "A.CSR Queries": 0, "A.CSR Rejection %": 0, "A.CPT Conversion %": 0.774,
        "T.CSR Rejection %": 0.005, "T.Queries Target": 0.002, "T.Attended C.R": 0.9,
        "Performance Score": 0.772, "Performance Grade": "Below average",
        "Serving Time (min)": 4.04, "No of Complaints": 1,
    }])
    no_complaints = csr.iloc[0].copy()
    no_complaints["HR ID"] = "SGHS00004"
    no_complaints["No of Complaints"] = 0
    no_complaints["Performance Score"] = 0.972
    no_complaints["Performance Grade"] = "Meet Expectations"
    csr = pd.concat([csr, no_complaints.to_frame().T], ignore_index=True)

    medical = pd.DataFrame([
        {"Date": pd.Timestamp("2026-10-01"), "HR ID": "SGHD00002", "Employee Name": "Test Doctor",
         "Branch": "Dubai", "Performance Score": 0.95, "Performance Grade": "Meet Expectations"},
        {"Date": pd.Timestamp("2026-10-01"), "HR ID": "SGHD00003", "Employee Name": "No Score",
         "Branch": "Dubai", "Performance Score": None, "Performance Grade": None},
    ])
    blob = io.BytesIO()
    with pd.ExcelWriter(blob, engine="openpyxl") as writer:
        csr.to_excel(writer, sheet_name="CSR", index=False)
        medical.to_excel(writer, sheet_name="Radiologist", index=False)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        result = DatabaseSeeder().process_uploaded_file("PMS.xlsx", blob.getvalue(), db_session=db)
        assert result["records_imported"] == 3
        assert set(result["teams"]) == {"CSR", "Radiologist"}
        assert db.query(PerformanceRecord).count() == 3
        assert db.query(Team).filter_by(name="Radiologist").one().region == "UAE"

        records = DashboardRecordService(db).list_records()
        by_id = {record.employee_id: record for record in records}
        assert (by_id["SGHS00001"].evaluation.score, by_id["SGHS00001"].evaluation.grade) == (77.2, "D")
        assert (by_id["SGHS00004"].evaluation.score, by_id["SGHS00004"].evaluation.grade) == (97.2, "B")
        kpis = {row["kpi_key"]: row for row in by_id["SGHS00001"].kpi_values}
        assert (kpis["ServingTime"]["actual_value"], kpis["ServingTime"]["unit"]) == (4.04, "min")
        assert kpis["Complaints"]["contribution"] == -0.20
        assert (by_id["SGHD00002"].evaluation.score, by_id["SGHD00002"].evaluation.grade) == (95.0, "B")
    engine.dispose()


def test_all_three_clinical_trends_keep_source_scores_and_skip_unscored_rows():
    october = pd.Timestamp("2026-10-01")
    september = pd.Timestamp("2026-09-01")
    blob = io.BytesIO()
    with pd.ExcelWriter(blob, engine="openpyxl") as writer:
        er = writer.book.create_sheet("ER Dr")
        er.append(["Date", "HR ID", "Performance Score", "Performance Grade", "A.No Re-visit within 72 hours"])
        er.append([september, "SGHD00101", 0.60, "Unsatisfactory", 7, None,
                   "Report Month", "Location", "EmpID", "Emp Name", "No Re-visit within 24 hours",
                   "Performance Score", "Performance Grade"])
        er.append([None] * 6 + [october, "Dubai", "SGHD00102", "ER doctor", 1, 0.82, "Average"])
        er.append([None] * 6 + [october, "Dubai", "SGHD00103", "ER doctor without score", 0, None, None])

        columns = ["Date", "HR ID", "Employee Name", "Branch", "Performance Score", "Performance Grade"]
        pd.DataFrame([
            [october, "SGHD00104", "Radiologist", "Dubai", 0.97, "Meet Expectations"],
        ], columns=columns).to_excel(writer, sheet_name="Radiologist", index=False)
        pd.DataFrame([
            [october, "SGHD00105", "Quality reviewer", "Dubai", 0.69, "Below average"],
            [october, "SGHD00106", "Quality reviewer without score", "Dubai", None, None],
        ], columns=columns).to_excel(writer, sheet_name="Qlty&Case-Mngt", index=False)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        result = DatabaseSeeder().process_uploaded_file("PMS.xlsx", blob.getvalue(), db_session=db)
        assert result["records_imported"] == 3
        records = DashboardRecordService(db).list_records()
        assert {r.team: (r.evaluation.score, r.evaluation.grade) for r in records} == {
            "ER Dr": (82.0, "C"), "Radiologist": (97.0, "B"), "Qlty&Case-Mngt": (69.0, "D"),
        }
        er_record = next(r for r in records if r.team == "ER Dr")
        assert er_record.branch_key == "dubai"
        assert er_record.raw_data["No Re-visit within 24 hours"] == 1
        assert "A.No Re-visit within 72 hours" not in er_record.raw_data
        assert all(r.month == "October" and r.year == 2026 for r in records)
    engine.dispose()
