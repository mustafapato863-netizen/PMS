"""Management monthly targets already live on ManagementKPIConfig.

Uses a disposable in-memory SQLite database. It does not read or write the
application database.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.models import Base, Team
from services.management_bsc_service import ManagementBSCService


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _base_config():
    return {
        "grade_thresholds": {"A": 90, "B": 80, "C": 70, "D": 60},
        "balanced_scorecard": {
            "enabled": True,
            "perspectives": [
                {"key": "Financial", "label": "Financial", "display_order": 1},
                {"key": "Customer", "label": "Customer", "display_order": 2},
                {"key": "Internal Process", "label": "Internal Process", "display_order": 3},
                {"key": "Learning & Growth", "label": "Learning & Growth", "display_order": 4},
            ],
            "strategy_map_links": [],
        },
    }


def _row(month: str, target: float) -> dict:
    return {
        "employee_id": "SYNTH-ATTEND-1",
        "team": "EvalBaseline",
        "employee_name": "Synthetic Attendance",
        "position": "Coverage Manager",
        "performance_level": "Managerial",
        "month": month,
        "year": 2026,
        "perspective": "Financial",
        "kpi_label": "Attendance",
        "direction": "higher_better",
        "weight": 1.0,
        "target_value": target,
        "target_unit": "%",
        "actual_value": 60.0,
    }


def _attendance(data: dict) -> dict:
    return next(row for row in data["kpi_table"] if row["kpi_label"] == "Attendance")


def test_july_and_august_management_snapshots_keep_separate_targets():
    session = _session()
    try:
        session.add(
            Team(
                id=uuid.uuid4(),
                name="EvalBaseline",
                db_name="EvalBaseline",
                display_name="EvalBaseline",
                region="UAE",
                team_level="management",
            )
        )
        session.commit()
        service = ManagementBSCService(session)
        service.import_template_rows(
            rows=[_row("July", 55.0), _row("August", 65.0)],
            updated_by="phase0-baseline",
        )

        july = service.build_scorecard_dataset(
            team_name="EvalBaseline",
            performance_level="Managerial",
            month="July",
            year=2026,
            employee_ids=["SYNTH-ATTEND-1"],
            history_months=1,
            selected_kpi="attendance",
            base_config=_base_config(),
        )
        august = service.build_scorecard_dataset(
            team_name="EvalBaseline",
            performance_level="Managerial",
            month="August",
            year=2026,
            employee_ids=["SYNTH-ATTEND-1"],
            history_months=1,
            selected_kpi="attendance",
            base_config=_base_config(),
        )
        july_again = service.build_scorecard_dataset(
            team_name="EvalBaseline",
            performance_level="Managerial",
            month="July",
            year=2026,
            employee_ids=["SYNTH-ATTEND-1"],
            history_months=1,
            selected_kpi="attendance",
            base_config=_base_config(),
        )

        july_kpi = _attendance(july)
        august_kpi = _attendance(august)
        assert july["selection"]["effective_month"] == "July"
        assert august["selection"]["effective_month"] == "August"
        assert july_kpi["target_value"] == 55.0
        assert august_kpi["target_value"] == 65.0
        assert july_kpi["actual_value"] == 60.0
        assert august_kpi["actual_value"] == 60.0
        assert july_kpi["score"] == pytest.approx(60.0 / 55.0 * 100.0)
        assert august_kpi["score"] == pytest.approx(60.0 / 65.0 * 100.0)
        assert _attendance(july_again)["target_value"] == 55.0
        assert _attendance(july_again)["score"] == july_kpi["score"]
    finally:
        session.close()
