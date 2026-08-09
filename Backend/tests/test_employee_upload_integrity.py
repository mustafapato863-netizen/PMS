import datetime
import uuid

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.database import Base
from models.models import (
    Employee,
    EmployeeUploadBatch,
    PerformanceRecord,
    Team,
    UploadLog,
)
from repositories.employee_upload_repository import EmployeeUploadRepository
from services.kpi_service import KPIService
from services.legacy_kpi_evidence import build_legacy_employee_kpi_values


class _EmptyConfigRepository:
    def get_by_team(self, _team):
        return None


def _kpi_service():
    empty = _EmptyConfigRepository()
    return KPIService(empty, empty)


def test_inbound_june_missing_quality_does_not_poison_reweighted_score():
    row = {
        "Date": datetime.datetime(2026, 6, 1),
        "TotalHandledCalls": 100,
        "Dubai_Booking": 45,
        "Dubai_Attend": 33.75,
        "InboundCalls": 100,
        "AbandonedCalls": 0,
        "A.QualityScore": np.nan,
        "A.UTZ%": 0.85,
        "AHT_Minutes": 2.5,
    }

    score, grade, achievements, weights = _kpi_service().calculate_performance("Inbound", row)

    assert score == 100
    assert grade == "A"
    assert achievements["Quality"] == 0
    assert weights["Quality"] == 0
    assert weights["Other"] == 0.15


def test_inbound_kpi_evidence_uses_the_calculated_targets_and_dynamic_utz_label():
    row = {
        "Date": datetime.datetime(2026, 5, 1),
        "TotalHandledCalls": 100,
        "Dubai_Booking": 45,
        "Dubai_Attend": 30,
        "InboundCalls": 100,
        "AbandonedCalls": 0,
        "A.QualityScore": 0.977,
        "A.UTZ%": 0.821,
        "AHT_Minutes": 2.7333333333,
    }

    _score, _grade, achievements, weights = _kpi_service().calculate_performance("Inbound", row)
    evidence = build_legacy_employee_kpi_values(
        "Inbound",
        row,
        achievements=achievements,
        weights=weights,
        config={"kpis": []},
    )
    by_key = {item["kpi_key"]: item for item in evidence}

    assert by_key["Attendance"]["target_value"] == 0.75
    assert by_key["Booking"]["target_value"] == 0.45
    assert by_key["Quality"]["target_value"] == 0.95
    assert by_key["AHT"]["target_value"] == 2.5
    assert by_key["Other"]["label"] == "Utilization"
    assert by_key["Other"]["target_value"] == 0.85
    assert by_key["Attendance"]["weight_applied"] == 0.70
    assert by_key["Quality"]["weight_applied"] == 0.05


def test_sales_kpi_evidence_preserves_volume_targets_and_contributions():
    row = {
        "A.OPCensus": 1085,
        "T.OPCensus": 1000,
        "A.OPRevenue": 1032,
        "T.OPRevenue": 1000,
        "A.IPCensus": 1096,
        "T.IPCensus": 1000,
        "A.IPRevenue": 835,
        "T.IPRevenue": 1000,
        "A.ClinicActivity": 4,
        "T.ClinicActivity": 3,
    }

    score, _, achievements, weights = _kpi_service().calculate_performance("Sales", row)
    evidence = {
        item["kpi_key"]: item
        for item in build_legacy_employee_kpi_values(
            "Sales", row, achievements=achievements, weights=weights, config={"kpis": []}
        )
    }

    assert score == pytest.approx(92.58)
    assert evidence["OPCensus"]["actual_value"] == 1085
    assert evidence["OPCensus"]["target_value"] == 1000
    assert evidence["IPRevenue"]["contribution"] == pytest.approx(0.37575)
    assert evidence["Activity"]["contribution"] == pytest.approx(0.1)


def test_outbound_june_missing_quality_uses_reachability_weight():
    row = {
        "Date": datetime.datetime(2026, 6, 1),
        "Reached": 100,
        "NumOfLeads": 100 / 0.75,
        "Dubai_Booking": 46,
        "Dubai_Attend": 25.3,
        "A.QualityScore": np.nan,
    }

    score, grade, achievements, weights = _kpi_service().calculate_performance("Outbound", row)

    assert score == 100
    assert grade == "A"
    assert achievements["Quality"] == 0
    assert weights["Quality"] == 0
    assert weights["Other"] == 0.20


def test_preapprovals_without_claims_excludes_error_and_uses_60_40_weights():
    row = {
        "SubmittedClaims": 0,
        "IPInitialRejection%": 0.06,
        "Error%": 0.99,
        "NumberApprovalwithin48hrs": 0.90,
    }

    score, grade, _achievements, weights = _kpi_service().calculate_performance(
        "Pre-Approvals IP Offshore", row
    )

    assert score == 70
    assert grade == "D"
    assert weights == {"Rejection": 0.60, "InitialError": 0, "Submission": 0.40}


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_upload_history_is_grouped_by_workbook_and_delete_respects_current_version():
    db = _db()
    team = Team(id=uuid.uuid4(), name="Inbound", db_name="Inbound", region="EGY")
    employee = Employee(
        id=uuid.uuid4(),
        employee_id="EMP-1",
        name="Employee One",
        team=team,
        region="EGY",
    )
    old_batch = EmployeeUploadBatch(
        id=uuid.uuid4(), filename="PMS_v1.xlsx", record_count=1, team_count=1, status="success"
    )
    new_batch = EmployeeUploadBatch(
        id=uuid.uuid4(), filename="PMS_v2.xlsx", record_count=1, team_count=1, status="success"
    )
    old_log = UploadLog(
        id=uuid.uuid4(), batch=old_batch, team=team, month="May", year=2026, record_count=1, status="success"
    )
    new_log = UploadLog(
        id=uuid.uuid4(), batch=new_batch, team=team, month="May", year=2026, record_count=1, status="success"
    )
    current = PerformanceRecord(
        id=uuid.uuid4(),
        year=2026,
        employee=employee,
        team_id=team.id,
        month="May",
        score=91,
        grade="B",
        status="Meets",
        upload_id=new_log.id,
    )
    db.add_all([team, employee, old_batch, new_batch, old_log, new_log, current])
    db.commit()

    repository = EmployeeUploadRepository(db)
    history = repository.list_batches()

    assert {item["filename"] for item in history} == {"PMS_v1.xlsx", "PMS_v2.xlsx"}
    assert all(item["teams"] == ["Inbound"] for item in history)
    assert all(item["periods"] == ["May 2026"] for item in history)

    assert repository.delete_batch(old_batch.id) == (1, 0)
    db.commit()
    assert db.query(PerformanceRecord).count() == 1

    assert repository.delete_batch(new_batch.id) == (1, 1)
    db.commit()
    assert db.query(PerformanceRecord).count() == 0
