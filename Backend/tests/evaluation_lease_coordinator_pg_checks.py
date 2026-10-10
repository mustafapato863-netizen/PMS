"""Opt-in PostgreSQL 16/18 checks for one evaluation lease claim.

This module is not named test_*.py, so a normal pytest collection does not
run it or reset a database. A reviewer runs it by path, one process at a
time, after other disposable-database work has stopped:

    python -X utf8 -m pytest -q -p no:cacheprovider tests/evaluation_lease_coordinator_pg_checks.py

The runner must already have APP_ENV=test, DATABASE_URL=sqlite:///:memory:,
and an empty REDIS_URL. Import does not connect, reset, or create containers.
Owned URLs are the disposable loopback pair from evaluation_history_pg_checks.
This slice does not execute this module.
"""

from __future__ import annotations

import importlib.util
import os
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

if os.environ.get("APP_ENV") != "test" or os.environ.get("DATABASE_URL") != "sqlite:///:memory:":
    raise RuntimeError(
        "evaluation_lease_coordinator_pg_checks requires APP_ENV=test and "
        "DATABASE_URL=sqlite:///:memory: from the runner before import. "
        "Owned PostgreSQL URLs are applied only for allowlisted connections."
    )
if os.environ.get("REDIS_URL", "") != "":
    raise RuntimeError("evaluation_lease_coordinator_pg_checks refuses a non-empty REDIS_URL.")

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from models.models import EvaluationApplyControl, EvaluationApplyStageRow, PerformanceRecord, ProcessingJob
from services.evaluation.lease_coordinator import EvaluationLeaseCoordinator, LeaseCoordinatorError


def _load(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FOUNDATION = _load("evaluation_apply_foundation_pg_checks.py", "evaluation_apply_foundation_pg_checks_for_lease")

pg = _FOUNDATION.pg
assert_public_search_path = _FOUNDATION.assert_public_search_path

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)


def _sessionmaker(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _actor(admin_id):
    return {
        "user_id": str(admin_id),
        "role": "Admin",
        "employee_id": "",
        "accessible_teams": [],
        "accessible_functions": [],
        "accessible_regions": [],
        "accessible_branches": [],
        "has_unrestricted_team_access": True,
        "legacy_unscoped": False,
    }


def _prepare(engine, target):
    session = _FOUNDATION._session(engine)
    try:
        with engine.connect() as connection:
            assert_public_search_path(connection, target)
        data = _FOUNDATION._seed(session)
        admin_id = data["admin"].id
        job_id = data["job"].id
        session.execute(
            text("UPDATE processing_jobs SET available_at = :moment WHERE id = :id"),
            {"moment": NOW, "id": job_id},
        )
        session.commit()
        return admin_id, job_id
    finally:
        session.close()


def _final(engine):
    session = _FOUNDATION._session(engine)
    try:
        job = session.query(ProcessingJob).one()
        control = session.query(EvaluationApplyControl).one()
        score = session.query(PerformanceRecord).one().score
        stages = session.query(EvaluationApplyStageRow).count()
        return job.status, control.state, job.worker_id, int(job.attempt_count or 0), score, stages
    finally:
        session.close()


def test_two_connections_let_one_start_win(pg):
    """One specified job has one winner. SQLite cannot certify this race."""

    engine, target = pg
    admin_id, job_id = _prepare(engine, target)
    actor = _actor(admin_id)
    barrier = threading.Barrier(2)
    winners = []
    errors = []

    def claim(worker):
        session = _sessionmaker(engine)()
        try:
            session.execute(text("SET statement_timeout = '8000ms'"))
            coordinator = EvaluationLeaseCoordinator(session, clock=lambda: NOW)
            barrier.wait(5)
            body = coordinator.start(actor, job_id, worker, lease_seconds=30, enabled=True)
            winners.append(body["worker_id"])
        except Exception as exc:
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=claim, args=(worker,)) for worker in ("worker-a", "worker-b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert all(not thread.is_alive() for thread in threads)
    assert winners == ["worker-a"] or winners == ["worker-b"]
    assert len(errors) == 1
    assert isinstance(errors[0], LeaseCoordinatorError)
    assert errors[0].code in {"lease_held", "invalid_state"}
    status, state, worker, attempts, score, stages = _final(engine)
    assert status == "running" and state == "staging"
    assert worker in {"worker-a", "worker-b"} and attempts == 1
    assert score == Decimal("70.00") and stages == 0


def test_cancel_and_start_serialize_on_the_team_fence(pg):
    """The shared team lock leaves one cancelled header, never a torn pair."""

    engine, target = pg
    admin_id, job_id = _prepare(engine, target)
    actor = _actor(admin_id)
    barrier = threading.Barrier(2)
    errors = []

    def start():
        session = _sessionmaker(engine)()
        try:
            session.execute(text("SET statement_timeout = '8000ms'"))
            coordinator = EvaluationLeaseCoordinator(session, clock=lambda: NOW)
            barrier.wait(5)
            coordinator.start(actor, job_id, "worker-a", lease_seconds=30, enabled=True)
        except Exception as exc:
            errors.append(exc)
        finally:
            session.close()

    def cancel():
        session = _sessionmaker(engine)()
        try:
            session.execute(text("SET statement_timeout = '8000ms'"))
            coordinator = EvaluationLeaseCoordinator(session, clock=lambda: NOW)
            barrier.wait(5)
            coordinator.cancel(actor, job_id, enabled=True)
        except Exception as exc:
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=start), threading.Thread(target=cancel)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert all(not thread.is_alive() for thread in threads)
    assert all(isinstance(error, LeaseCoordinatorError) and error.code == "invalid_state" for error in errors)
    status, state, worker, _attempts, score, stages = _final(engine)
    assert (status, state) == ("cancelled", "cancelled")
    assert (status, state) not in {("queued", "staging"), ("running", "pending")}
    assert worker is None
    assert score == Decimal("70.00") and stages == 0
