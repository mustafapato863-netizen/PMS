import io
from datetime import date
from uuid import uuid4

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from config.database import Base
from models.models import KPIValue, PerformanceRecord, Team
from scripts.prepare_csr_source_upload import SOURCE_TABS, prepare_upload
from services.dashboard_record_service import DashboardRecordService
from services.performance_dashboard_read_service import PerformanceDashboardReadService, _summary
from services.scoring.monthly_official_scores import official_team_score
from services.seeding_service import DatabaseSeeder
from services.csr_sharjah_scoring import score_sharjah_csr, uses_sharjah_csr_score
from services.uae_published_scores import has_published_score_columns


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
                   "Report Month", "Location", "EmpID", "Emp Name", "No Re-visit within 24 hours", "Valid Complains",
                   "Performance Score", "Performance Grade"])
        er.append([None] * 6 + [october, "Dubai", "SGHD00102", "ER doctor", 1, 0, 0.82, "Average"])
        er.append([None] * 6 + [october, "Dubai", "SGHD00103", "ER doctor without score", 0, None, None, None])

        columns = ["Date", "HR ID", "Employee Name", "Branch", "Performance Score", "Performance Grade"]
        pd.DataFrame([
            [october, "SGHD00104", "Radiologist", "Dubai", 0.97, "Meet Expectations", 0.85],
        ], columns=columns + ["Ach.TAT %"]).to_excel(writer, sheet_name="Radiologist", index=False)
        pd.DataFrame([
            [october, "SGHD00105", "Quality reviewer", "Dubai", 0.69, "Below average", 0.72],
            [october, "SGHD00106", "Quality reviewer without score", "Dubai", None, None, None],
        ], columns=columns + ["Case Management Rate"]).to_excel(writer, sheet_name="Qlty&Case-Mngt", index=False)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        result = DatabaseSeeder().process_uploaded_file("PMS.xlsx", blob.getvalue(), db_session=db)
        assert result["records_imported"] == 3
        records = DashboardRecordService(db).list_records()
        assert {r.team: (r.evaluation.score, r.evaluation.grade) for r in records} == {
            "ER Dr": (82.0, "C"), "Radiologist": (97.0, "B"), "Qlty&Case-Mngt": (69.0, "D"),
        }
        expected = {"ER Dr": 0.0, "Radiologist": 0.85, "Qlty&Case-Mngt": 0.72}
        def observations(rows):
            return {r.team: [v["actual_value"] for v in r.kpi_values if v.get("view_only")] for r in rows}
        assert observations(records) == {team: [value] for team, value in expected.items()}
        # Existing imports only have the summary KPI persisted.
        db.query(KPIValue).filter(KPIValue.kpi_key != "PerformanceScore").delete()
        db.commit()
        assert observations(DashboardRecordService(db).list_records()) == observations(records)
        er_record = next(r for r in records if r.team == "ER Dr")
        assert er_record.branch_key == "dubai"
        assert er_record.raw_data["No Re-visit within 24 hours"] == 1
        assert "A.No Re-visit within 72 hours" not in er_record.raw_data
        assert all(r.month == "October" and r.year == 2026 for r in records)
    engine.dispose()


def test_published_scores_only_apply_to_dated_uae_employee_sheets():
    fields = {"Date": "2026-10-01", "Role": "Employee", "PerformanceScore": 1, "PerformanceGrade": "A"}
    assert has_published_score_columns("Coding", "UAE", "Employee", fields)
    assert not has_published_score_columns("Coding", "EGY", "Employee", fields)
    assert not has_published_score_columns("Coding", "UAE", "Managerial", fields)
    assert not has_published_score_columns("Coding", "UAE", "Employee", {**fields, "Date": "2026-09-01"})
    assert not has_published_score_columns("Coding", "UAE", "Employee", {k: v for k, v in fields.items() if k != "Role"})


def test_prepared_csr_scorecards_keep_source_totals_branches_and_zero(tmp_path, monkeypatch):
    report = Workbook()
    report.remove(report.active)
    inputs = [
        ("SGHD00001", 1, "Meet Expectations", "dubai"),
        ("SGHD00002", 0.9, "Average", "dubai"),
        ("SGHA00003", 0, "Unsatisfactory", "ajman"),
        ("SGHS00004", 0.005, "Unsatisfactory", "sharjah"),
    ]
    for (tab, (_, columns)), (employee, score, grade, _) in zip(SOURCE_TABS.items(), inputs, strict=True):
        worksheet = report.create_sheet(tab)
        for column, label in columns.values():
            worksheet[f"{column}2"] = label
        for key, value in {
            "HR ID": employee, "Agent Name": f"Test {tab}", "Status": "Active", "Performance Score": score,
            "Performance Grade": grade, "A.CSR Queries": 0, "T.Queries Target": 0.002,
        }.items():
            worksheet[f"{columns[key][0]}3"] = value
        worksheet[f"{columns['HR ID'][0]}4"] = "SGHD99999"
        worksheet[f"{columns['Agent Name'][0]}4"] = "No published score"
    source = tmp_path / "report.xlsx"
    upload = tmp_path / "upload.xlsx"
    report.save(source)
    assert prepare_upload(source, date(2026, 10, 1), upload) == 4

    # A dated trend upload can also contain an unscored row with real KPI counters.
    sheet = load_workbook(upload)
    sheet.active.append([date(2026, 10, 1), "UAE", "Employee", "Dubai", None,
                         "SGHD99999", "No published score", "Active", 25])
    sheet.save(upload)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        legacy = io.BytesIO()
        with pd.ExcelWriter(legacy, engine="openpyxl") as writer:
            pd.DataFrame([{
                "Date": pd.Timestamp("2026-10-01"), "Region": "UAE", "Role": "Emp", "Team": "Dubai",
                "HR ID": "SGHD99998", "Agent Name": "Previously Calculated", "Status": "Inactive",
                "A.CSR Rejection %": 0.001, "T.CSR Rejection %": 0.005,
                "Performance Score": None, "Performance Grade": "Inactive Staff",
            }]).to_excel(writer, sheet_name="CSR", index=False)
        with monkeypatch.context() as baseline:
            baseline.setattr("services.seeding_service.has_published_score_columns", lambda *_: False)
            assert DatabaseSeeder().process_uploaded_file("legacy.xlsx", legacy.getvalue(), db_session=db)["records_imported"] == 1
        assert float(db.query(PerformanceRecord).one().score) == 40

        result = DatabaseSeeder().process_uploaded_file("csr.xlsx", upload.read_bytes(), db_session=db)
        assert result["records_imported"] == 4
        assert db.query(PerformanceRecord).count() == 5
        records = DashboardRecordService(db).list_records()
        by_id = {record.employee_id: record for record in records}
        assert set(by_id) == {employee for employee, *_ in inputs}
        for employee, score, _grade, branch in inputs:
            assert by_id[employee].evaluation.score == score * 100
            assert by_id[employee].branch_key == branch
        assert by_id["SGHD00001"].evaluation.grade == "B"
        assert by_id["SGHD00002"].evaluation.grade == "C"
        assert by_id["SGHD00002"].raw_data["CSRSourceSheet"] == "CSR - ER - Dubai"
        observation = next(kpi for kpi in by_id["SGHD00001"].kpi_values if kpi["kpi_key"] == "Queries")
        assert observation["actual_value"] == 0
        assert observation["direction"] == "lower_better"
        assert observation["view_only"] is True

        dashboard = _summary(records, "all")
        assert (dashboard["total_agents"], dashboard["average_score"]) == (4, 47.62)
        review = official_team_score(records, "CSR")
        assert (review.sample_size, review.score, review.score_basis) == (4, 47.6, "average published employee scores")

        service = PerformanceDashboardReadService(db, {
            "user_id": str(uuid4()), "role": "Manager", "accessible_teams": ["CSR"],
        })
        page = service.records_page(period="2026-10", team="CSR", score_lt=1, sort="score_asc", page_size=1)
        second = service.records_page(period="2026-10", team="CSR", score_lt=1, sort="score_asc", page_size=1,
                                      cursor=page["next_cursor"])
        assert page["items"][0]["score"] == 0
        assert second["items"][0]["score"] == 0.5
        assert "ScoringMethod" in second["items"][0]["raw_data"]
    engine.dispose()
