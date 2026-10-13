"""Capture one synthetic dataset through the two summary read paths.

The Executive page reads ``/api/performance/summary`` (one request per filter
set). The Departmental page falls back to ``/api/performance/summary-records``
and composes the summary in the browser. This module seeds one in-memory SQLite
dataset, calls those endpoints the same way the pages do, and writes every raw
response into one bundle for the frontend parity test.

Synthetic names, ids and numbers only. The Outbound employee scores are the
reviewed evaluation values (July 82.85, August 79.82) so the anchor matches the
golden figures asserted in ``test_evaluation_workflow_consumer.py``.

Writes only when ``PMS_SUMMARY_PARITY_OUT`` names a directory; otherwise skipped.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import Action, Employee, PerformanceRecord, Team

OUT_ENV = "PMS_SUMMARY_PARITY_OUT"
# Pipeline values before storage. `performance_records.score` is Numeric(6, 2),
# so the persisted anchor is the two-decimal value the QA review quotes.
GOLDEN_JULY = 82.85143792679492
GOLDEN_AUGUST = 79.82419863297692
STORED_JULY = round(GOLDEN_JULY, 2)
STORED_AUGUST = round(GOLDEN_AUGUST, 2)

FILTER_SETS: list[dict[str, str]] = [
    {},
    {"region": "EGY"},
    {"region": "UAE"},
    {"location": "dubai"},
    {"location": "sharjah"},
    {"location": "ajman"},
    {"location": "clinics"},
    {"performance_level": "Employee"},
    {"performance_level": "Managerial"},
    {"region": "EGY", "location": "dubai"},
]
PERIODS = ["2026-07", "2026-08", "2026-09"]


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db):
    teams = {
        "Outbound": Team(id=uuid.uuid4(), name="Outbound", db_name="outbound", display_name="Outbound", region="EGY", team_level="employee", is_active=True),
        "Inbound": Team(id=uuid.uuid4(), name="Inbound", db_name="inbound", display_name="Inbound", region="EGY", team_level="employee", is_active=True),
        "Coding": Team(id=uuid.uuid4(), name="Coding", db_name="coding", display_name="Coding", region="UAE", team_level="employee", is_active=True),
    }
    db.add_all(teams.values())
    db.flush()
    people = {
        "TA-OB-01": ("Test Agent OB-01", "Outbound", "EGY"),
        "TA-OB-02": ("Test Agent OB-02", "Outbound", "EGY"),
        "TA-IB-01": ("Test Agent IB-01", "Inbound", "EGY"),
        "TA-IB-02": ("Test Agent IB-02", "Inbound", "EGY"),
        "TA-IB-03": ("Test Agent IB-03", "Inbound", "EGY"),
        "TA-CD-01": ("Test Agent CD-01", "Coding", "UAE"),
        "TA-CD-02": ("Test Agent CD-02", "Coding", "UAE"),
    }
    employees = {
        code: Employee(id=uuid.uuid4(), employee_id=code, name=name, team_id=teams[team].id, region=region)
        for code, (name, team, region) in people.items()
    }
    db.add_all(employees.values())
    db.flush()

    def row(code, year, month, score, grade, *, level="Employee", branch=None, raw_branch=None, region=None):
        payload = {"raw_data": {"Branch": raw_branch}} if raw_branch else None
        return PerformanceRecord(
            id=uuid.uuid4(), year=year, month=month, employee_id=employees[code].id,
            team_id=teams[people[code][1]].id, performance_level=level,
            region=region or people[code][2], branch_key=branch, score=score, grade=grade,
            status="Meets", record_payload=payload,
        )

    rows = [
        # Outbound: reviewed anchor scores (July 82.85, August 79.82) plus a second employee.
        row("TA-OB-01", 2026, "July", STORED_JULY, "C"),
        row("TA-OB-01", 2026, "August", STORED_AUGUST, "D"),
        row("TA-OB-02", 2026, "July", 91.2, "B"),
        row("TA-OB-02", 2026, "August", 88.4, "C"),
        # Inbound: spread of grades, one zero-activity row, one 0-10 scale value (edge).
        row("TA-IB-01", 2026, "July", 97.5, "A", branch="dubai"),
        row("TA-IB-01", 2026, "August", 84.0, "C", branch="dubai"),
        row("TA-IB-02", 2026, "July", 71.0, "D", raw_branch="SHJ AJM"),
        row("TA-IB-02", 2026, "August", 63.0, "E", raw_branch="SHJ AJM"),
        row("TA-IB-03", 2026, "August", 0, "E"),
        row("TA-IB-03", 2026, "September", 0, "E"),
        # Coding (UAE): branch_key disagrees with the raw branch text (data-quality edge).
        row("TA-CD-01", 2026, "July", 92.0, "B", branch="dubai", region="UAE"),
        row("TA-CD-01", 2026, "August", 90.0, "B", region="UAE"),
        row("TA-CD-02", 2026, "July", 74.0, "D", branch="dubai", raw_branch="SHJ", region="UAE"),
        row("TA-CD-02", 2026, "August", 5.5, "E", raw_branch="SHJ", region="UAE"),
        row("TA-CD-02", 2026, "July", 66.0, "E", level="Managerial", branch="clinics", region="UAE"),
    ]
    db.add_all(rows)
    db.commit()
    return teams, employees


def _seed_actions(db, teams, employees):
    def action(code, team, month, year, action_type, text, note, created, *, status="Open", linked=None):
        return Action(
            id=uuid.uuid4(), employee_id=employees[code].id, team_id=teams[team].id, month=month, year=year,
            action_type=action_type, action_text=text, root_cause_note=note, status=status,
            linked_kpi_key=linked, created_at=created, updated_at=created, is_active=True,
        )

    july = datetime(2026, 7, 15, tzinfo=timezone.utc)
    august = datetime(2026, 8, 12, tzinfo=timezone.utc)
    old_july = datetime(2025, 7, 9, tzinfo=timezone.utc)
    rows = [
        action("TA-OB-01", "Outbound", "July", 2026, "Coaching", "Coaching on call quality", "Quality score below target", july),
        action("TA-OB-01", "Outbound", "July", 2026, "PIP", "Performance plan", "AHT above target and quality score", july, status="Completed"),
        action("TA-OB-02", "Outbound", "July", 2026, "Training", "Booking skills course", "Booking CR low", july, linked="quality_score"),
        action("TA-IB-01", "Inbound", "July", 2026, "Reward", "Recognition", "", july),
        action("TA-IB-02", "Inbound", "July", 2026, "Monitor", "Weekly check", "Abandon rate and reachability", july),
        action("TA-IB-02", "Inbound", "August", 2026, "Coaching", "Call handling", "AHT", august, status="In Progress"),
        action("TA-CD-01", "Coding", "July", 2026, "Training", "Coding refresher", "Initial error rate", july),
        action("TA-CD-02", "Coding", "July", 2025, "PIP", "Legacy July action", "Submission rate", old_july),
    ]
    db.add_all(rows)
    db.commit()


def _auth_app(db, monkeypatch):
    from fastapi import FastAPI
    from api.middleware.auth_middleware import AuthMiddleware
    from api.routers.performance import router as performance_router
    from api.routers.users_and_actions import actions_router
    from config import settings
    from config.database import get_db
    from services.auth_service import AuthenticationService
    from services.cache_service import CacheService

    admin = AuthenticationService.create_user(db, "parity_admin", "parity-admin@example.test", "SecurePassword123!", "Admin")
    db.commit()
    token = AuthenticationService.authenticate_user(db, admin.username, "SecurePassword123!")
    headers = {"Authorization": f"Bearer {token}"}
    monkeypatch.setattr(settings, "PMS_SCOPED_PERFORMANCE_API_ENABLED", True)
    monkeypatch.setattr(settings, "PMS_SCOPED_PERFORMANCE_ALLOWED_ROLES", ("Admin",))
    monkeypatch.setattr("api.middleware.auth_middleware._legacy_access_allowed", lambda: False)
    monkeypatch.setattr(CacheService, "get_json", lambda *_, **__: None)
    monkeypatch.setattr(CacheService, "set_json", lambda *_, **__: None)

    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.include_router(performance_router, prefix="/api")
    app.include_router(actions_router, prefix="/api/corrective-actions")
    return app, headers


def _key(period: str, filters: dict[str, str]) -> str:
    return "|".join([
        f"period={period}",
        f"region={filters.get('region', 'All')}",
        f"location={filters.get('location', 'all')}",
        f"performance_level={filters.get('performance_level', 'All')}",
    ])


def _data(response):
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("success") is True, body
    return body["data"]


@pytest.mark.skipif(not os.environ.get(OUT_ENV), reason=f"set {OUT_ENV} to capture the parity bundle")
def test_capture_summary_parity_bundle(monkeypatch):
    from fastapi.testclient import TestClient

    db = _session()
    try:
        teams, employees = _seed(db)
        _seed_actions(db, teams, employees)
        app, headers = _auth_app(db, monkeypatch)
        with TestClient(app) as client:
            catalog = _data(client.get("/api/performance/catalog", headers=headers))
            summaries = {}
            for period in PERIODS:
                for filters in FILTER_SETS:
                    params = {"period": period, "location": filters.get("location", "all"), "trend_months": 24}
                    if "region" in filters:
                        params["region"] = filters["region"]
                    if "performance_level" in filters:
                        params["performance_level"] = filters["performance_level"]
                    summaries[_key(period, filters)] = _data(client.get("/api/performance/summary", params=params, headers=headers))
            records = _data(client.get("/api/performance/summary-records", headers=headers))
            actions = _data(client.get("/api/corrective-actions/", headers=headers))
            follow_up = _data(client.get("/api/corrective-actions/follow-up", headers=headers))

        # The reviewed anchor: the persisted Outbound scores are the QA values at two decimals.
        stored = {(row.employee_id, row.month): float(row.score) for row in db.query(PerformanceRecord).all()}
        assert stored[(employees["TA-OB-01"].id, "July")] == pytest.approx(STORED_JULY)
        assert stored[(employees["TA-OB-01"].id, "August")] == pytest.approx(STORED_AUGUST)

        bundle = {
            "generated_by": "Backend/tests/test_summary_parity_capture.py",
            "synthetic": True,
            "periods": PERIODS,
            "filter_sets": FILTER_SETS,
            "catalog": catalog,
            "summaries": summaries,
            "summary_records": records,
            "corrective_actions": actions,
            "follow_up": follow_up,
        }
        out = Path(os.environ[OUT_ENV])
        out.mkdir(parents=True, exist_ok=True)
        (out / "parity-fixture.json").write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
    finally:
        db.close()
