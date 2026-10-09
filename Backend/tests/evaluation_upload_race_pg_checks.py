"""Explicit opt-in PostgreSQL upload-versus-correction concurrency check.

Uses only the predecessor fixture's verified disposable loopback database
allowlist. Not collected by normal test_*.py discovery. No production target.
"""
from __future__ import annotations

import importlib.util
import os
import threading
import time
import uuid
from pathlib import Path

if os.environ.get("APP_ENV") != "test" or os.environ.get("DATABASE_URL") != "sqlite:///:memory:":
    raise RuntimeError("Explicit upload-race checks require test mode and in-memory default database before import.")
if os.environ.get("REDIS_URL", "") != "":
    raise RuntimeError("Explicit upload-race checks refuse configured Redis.")

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from models.models import Employee as DBEmployee, EvaluationRevision, KPIValue, PerformanceRecord as DBRecord
from models.schemas import Employee, EvaluationData, PerformanceRecord
from services.evaluation.workflow import EvaluationWorkflow
from services.seeding_service import DatabaseSeeder

spec = importlib.util.spec_from_file_location(
    "owned_revision_pg", Path(__file__).with_name("evaluation_month_revision_pg_checks.py")
)
owned = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owned)
pg = owned.pg


def test_real_upload_holds_team_lock_and_invalidates_old_apply_proof(pg):
    engine, target = pg
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session() as setup:
        seeded = owned._seed(setup)
        employee_id = setup.query(DBEmployee).one().employee_id
        key = setup.query(KPIValue).one().kpi_key

    pinned = threading.Event()
    release = threading.Event()
    started = threading.Event()
    finished = threading.Event()
    outcomes = {}

    def upload():
        try:
            with Session() as session:
                session.execute(text("SET statement_timeout = '12s'"))
                record = PerformanceRecord(
                    id=f"{employee_id}_2026_July", employee_id=employee_id,
                    employee_name="Synthetic upload", team="Coding", month="July", year=2026,
                    region="UAE", performance_level="Employee", position="",
                    evaluation=EvaluationData(score=0, grade="E"),
                    kpi_values=[{"kpi_key": key, "actual_value": 52, "target_value": 65,
                                 "weight_applied": 1, "achievement_ratio": None, "contribution": None}],
                )
                person = Employee(id=employee_id, name="Synthetic upload", team="Coding",
                                  region="UAE", performance_level="Employee", position="")
                seeder = DatabaseSeeder()
                preview = seeder._pin_uploaded_records(session, [record])
                assert preview[0]["score"] == 80
                pinned.set()
                assert release.wait(15), "Upload transaction was not released"
                seeder._sync_to_database([record], [person], db_session=session)
                session.commit()
                outcomes["upload"] = "committed"
        except Exception as exc:
            outcomes["upload_error"] = repr(exc)
            pinned.set()

    def apply():
        try:
            with Session() as session:
                session.execute(text("SET statement_timeout = '12s'"))
                started.set()
                outcomes["apply"] = EvaluationWorkflow(session).apply(
                    seeded["actor"], seeded["scope_id"], 2026, 7
                )
        except Exception as exc:
            outcomes["apply_error"] = owned._describe(exc)
        finally:
            finished.set()

    uploader = threading.Thread(target=upload, name="owned-real-upload")
    applier = threading.Thread(target=apply, name="owned-correction")
    uploader.start()
    try:
        assert pinned.wait(15), "Real pin path did not finish"
        assert "upload_error" not in outcomes, outcomes
        applier.start()
        assert started.wait(15)
        # This bounded observation distinguishes an actual PostgreSQL row-lock
        # wait from a merely slow worker or a compiled SQL assertion.
        with engine.connect() as connection:
            owned.assert_safe(connection, target)
            deadline = time.monotonic() + 5
            while True:
                connection.execute(text("SELECT pg_stat_clear_snapshot()"))
                blocked = connection.execute(text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock' "
                    "AND query ILIKE '%teams%'"
                )).scalar_one()
                if blocked:
                    break
                assert not finished.is_set(), outcomes
                assert time.monotonic() < deadline, "Apply did not wait on upload's real team lock"
                threading.Event().wait(0.05)
        assert not finished.is_set(), outcomes
    finally:
        release.set()
        owned._join([uploader] + ([applier] if applier.ident else []))

    assert outcomes.get("upload") == "committed", outcomes
    assert outcomes.get("apply_error") == "EvaluationConflict:stale_preview", outcomes
    with Session() as verify:
        row = verify.query(DBRecord).filter(DBRecord.id == uuid.UUID(seeded["record_id"])).one()
        assert float(row.score) == 80
        assert row.record_payload["evaluation"]["score"] == 80
        values = verify.query(KPIValue).filter(KPIValue.record_id == row.id).all()
        assert len(values) == 1
        assert float(values[0].actual_value) == 52
        assert float(values[0].target_value) == 65
        assert verify.query(EvaluationRevision).count() == 0
