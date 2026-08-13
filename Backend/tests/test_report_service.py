import io
import uuid
import zipfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import GeneratedReport, SavedReportTemplate, User
from models.report_schemas import ReportConfiguration
from models.schemas import EvaluationData, PerformanceRecord
from services.report_service import ReportAccessError, ReportNotFoundError, ReportService, ReportValidationError


class StubRecordService:
    def __init__(self, records):
        self.records = records

    def list_records(self, **filters):
        return [
            record
            for record in self.records
            if all(value is None or str(getattr(record, key)) == str(value) for key, value in filters.items())
        ]


def _record(employee_id: str, team: str, level: str, month: str = "June") -> PerformanceRecord:
    return PerformanceRecord(
        id=f"{employee_id}_2026_{month}",
        employee_id=employee_id,
        employee_name=f"Employee {employee_id}",
        team=team,
        position="Analyst",
        region="EGY",
        performance_level=level,
        year=2026,
        month=month,
        status="Meets",
        evaluation=EvaluationData(score=91.5, grade="B"),
        kpi_values=[
            {
                "kpi_key": "quality",
                "label": "Quality",
                "actual_value": 95,
                "target_value": 90,
                "achievement_ratio": 1.055,
                "contribution": 0.25,
            }
        ],
    )


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[User.__table__, GeneratedReport.__table__, SavedReportTemplate.__table__],
    )
    session = sessionmaker(bind=engine)()
    user = User(
        id=uuid.uuid4(),
        username="report-admin",
        email="reports@example.com",
        password_hash="not-used",
        role="Admin",
    )
    session.add(user)
    session.commit()
    yield session, user
    session.close()


def _admin_scope(user: User) -> dict:
    return {
        "user": user,
        "user_id": str(user.id),
        "role": "Admin",
        "employee_id": user.employee_id,
        "accessible_teams": [],
        "accessible_team_levels": [],
        "is_general_manager": True,
        "legacy_unscoped": False,
    }


def _configuration(**overrides) -> ReportConfiguration:
    values = {
        "report_type": "team",
        "report_name": "June Team Report",
        "start_month": "June",
        "start_year": 2026,
        "team": "Marketing",
        "included_sections": ["summary", "kpi_breakdown", "details"],
    }
    values.update(overrides)
    return ReportConfiguration(**values)


def test_options_are_restricted_to_manager_team_and_level(db):
    session, _user = db
    service = ReportService(
        session,
        StubRecordService([
            _record("EMP1", "Marketing", "Employee"),
            _record("EMP2", "Marketing", "Managerial"),
            _record("EMP3", "Sales", "Employee"),
        ]),
    )
    scope = {
        "role": "Manager",
        "accessible_teams": ["Marketing"],
        "accessible_team_levels": [("Marketing", "Managerial")],
        "is_general_manager": False,
        "legacy_unscoped": False,
    }

    options = service.options(scope)

    assert options["teams"] == ["Marketing"]
    assert options["performance_levels"] == ["Managerial"]
    assert [employee["id"] for employee in options["employees"]] == ["EMP2"]
    assert options["can_export"] is True


def test_preview_uses_strict_period_without_falling_back(db):
    session, user = db
    service = ReportService(session, StubRecordService([_record("EMP1", "Marketing", "Employee", "May")]))

    with pytest.raises(ReportNotFoundError):
        service.preview(_configuration(), _admin_scope(user))


def test_generate_persists_real_pptx_and_selected_sections(db):
    session, user = db
    service = ReportService(session, StubRecordService([_record("EMP1", "Marketing", "Employee")]))

    report = service.generate(_configuration(), _admin_scope(user))

    assert report.record_count == 1
    assert report.output_format == "pptx"
    assert report.file_name == "June_Team_Report.pptx"
    assert session.query(GeneratedReport).count() == 1
    with zipfile.ZipFile(io.BytesIO(report.file_data)) as archive:
        assert "ppt/presentation.xml" in archive.namelist()
        assert "ppt/slides/slide1.xml" in archive.namelist()
        assert archive.read("ppt/slides/slide1.xml").startswith(b"<?xml")


def test_marketing_pptx_uses_selected_period_records_and_actions(db):
    session, user = db
    marketing_record = _record("EMP1", "Marketing", "Employee", "July")
    marketing_record.year = 2026
    marketing_record.position = "Media Buyer"
    marketing_record.evaluation.score = 61.0
    marketing_record.kpi_values = [{
        "kpi_key": "mb_leads",
        "label": "Leads",
        "unit": "count",
        "direction": "higher_better",
        "actual_value": 35,
        "target_value": 100,
        "achievement_ratio": 0.35,
        "weight_applied": 0.30,
    }]
    service = ReportService(session, StubRecordService([marketing_record]))
    service.actions.list_active = lambda: []

    report = service.generate(
        _configuration(
            report_type="team_marketing",
            report_name="July Marketing Summary",
            start_month="July",
            start_year=2026,
            team="Marketing",
            performance_level="Employee",
            included_sections=["summary", "details"],
        ),
        _admin_scope(user),
    )

    assert report.output_format == "pptx"
    assert report.file_name == "July_Marketing_Summary.pptx"
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(report.file_data))
    slide_text = "\n".join(
        shape.text
        for slide in presentation.slides
        for shape in slide.shapes
        if hasattr(shape, "text")
    )
    assert "July 2026" in slide_text
    assert "Leads" in slide_text
    assert "61.0%" in slide_text
    assert "June 2026" not in slide_text


def test_generate_pdf_export_uses_pdf_content_type(db):
    session, user = db
    service = ReportService(
        session,
        StubRecordService([_record("EMP1", "Marketing", "Employee")]),
    )

    report = service.generate(_configuration(output_format="pdf"), _admin_scope(user))

    assert report.output_format == "pdf"
    assert report.file_name == "June_Team_Report.pdf"
    assert report.content_type == "application/pdf"
    assert report.file_data.startswith(b"%PDF-1.4")


def test_generate_rejects_team_outside_scope(db):
    session, user = db
    service = ReportService(session, StubRecordService([_record("EMP1", "Marketing", "Employee")]))
    scope = _admin_scope(user) | {
        "role": "Manager",
        "is_general_manager": False,
        "accessible_teams": ["Sales"],
    }

    with pytest.raises(ReportAccessError):
        service.generate(_configuration(), scope)


def test_generate_rolls_back_when_persistence_fails(db, monkeypatch):
    session, user = db
    service = ReportService(session, StubRecordService([_record("EMP1", "Marketing", "Employee")]))

    def fail_after_add(report):
        session.add(report)
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(service.reports, "add_generated", fail_after_add)

    with pytest.raises(RuntimeError, match="storage unavailable"):
        service.generate(_configuration(), _admin_scope(user))

    assert session.query(GeneratedReport).count() == 0


def test_delete_generated_removes_the_authorized_report(db):
    session, user = db
    service = ReportService(session, StubRecordService([_record("EMP1", "Marketing", "Employee")]))
    report = service.generate(_configuration(), _admin_scope(user))

    deleted = service.delete_generated(str(report.id), _admin_scope(user))

    assert deleted == {"id": str(report.id), "name": "June Team Report"}
    assert session.query(GeneratedReport).count() == 0


def test_delete_generated_rejects_an_unknown_report(db):
    session, user = db
    service = ReportService(session, StubRecordService([]))

    with pytest.raises(ReportNotFoundError, match="not found"):
        service.delete_generated(str(uuid.uuid4()), _admin_scope(user))


def test_saved_template_contains_configuration_only_and_rejects_duplicates(db):
    session, user = db
    service = ReportService(session, StubRecordService([_record("EMP1", "Marketing", "Employee")]))
    configuration = _configuration()

    saved = service.save_template("Monthly Marketing", configuration, _admin_scope(user))

    assert saved.configuration["team"] == "Marketing"
    assert "file_data" not in saved.configuration
    with pytest.raises(ReportValidationError, match="already exists"):
        service.save_template("Monthly Marketing", configuration, _admin_scope(user))
