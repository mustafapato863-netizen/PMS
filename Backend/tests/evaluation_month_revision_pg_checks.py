"""Explicit PostgreSQL checks for the month-correction workflow.

This module is not named test_*.py, so a normal pytest collection does not
run it or drop schemas. Run it by path from Backend:

    python -X utf8 -m pytest -q -p no:cacheprovider tests/evaluation_month_revision_pg_checks.py

The runner must already have APP_ENV=test, DATABASE_URL=sqlite:///:memory:,
and an empty REDIS_URL. Owned PostgreSQL URLs are used only inside the
allowlisted fixture. This file does not write os.environ.
"""

from __future__ import annotations

import importlib.util
import copy
import os
import threading
import uuid
from decimal import Decimal
from pathlib import Path

if os.environ.get("APP_ENV") != "test" or os.environ.get("DATABASE_URL") != "sqlite:///:memory:":
    raise RuntimeError(
        "evaluation_month_revision_pg_checks requires APP_ENV=test and "
        "DATABASE_URL=sqlite:///:memory: from the runner before import. "
        "Owned PostgreSQL URLs are applied only for allowlisted connections."
    )
if os.environ.get("REDIS_URL", "") != "":
    raise RuntimeError("evaluation_month_revision_pg_checks refuses a non-empty REDIS_URL.")

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from config.database import Base
from models.models import Employee, EvaluationRevision, KPIValue, PerformanceRecord, Team, TeamConfigurationVersion, User
from services.evaluation.workflow import EvaluationConflict, EvaluationError, EvaluationWorkflow


def _load_history_helpers():
    path = Path(__file__).with_name("evaluation_history_pg_checks.py")
    spec = importlib.util.spec_from_file_location("evaluation_history_pg_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_HISTORY = _load_history_helpers()
TARGETS = _HISTORY.TARGETS
assert_safe = _HISTORY.assert_safe
reset_public = _HISTORY.reset_public
url_for = _HISTORY.url_for


def _actor(user: User) -> dict:
    return {
        "user_id": str(user.id),
        "role": user.role,
        "employee_id": "",
        "accessible_teams": [],
        "accessible_functions": [],
        "accessible_regions": [],
        "accessible_branches": [],
        "has_unrestricted_team_access": True,
        "legacy_unscoped": False,
    }


def _line_edit(lines: list[dict], target: float) -> list[dict]:
    edited = []
    for index, line in enumerate(lines):
        edited.append({
            **line,
            "weight": 1 if index == 0 else 0,
            "direction": "higher_better",
            "target_mode": "fixed",
            "target": target if index == 0 else 1,
        })
    return edited


def _describe(exc: Exception) -> str:
    code = getattr(exc, "data", {}).get("code") if hasattr(exc, "data") else None
    return f"{exc.__class__.__name__}:{code}"


def _join(threads: list[threading.Thread]) -> None:
    for thread in threads:
        thread.join(20)
    alive = [thread.name for thread in threads if thread.is_alive()]
    assert alive == []


@pytest.fixture(params=list(TARGETS), ids=lambda item: item["name"])
def pg(request, monkeypatch):
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda self, kind: None)
    target = request.param
    engine = create_engine(url_for(target), poolclass=NullPool)
    with engine.connect() as connection:
        reset_public(connection, target)
    Base.metadata.create_all(bind=engine)
    with engine.connect() as connection:
        assert_safe(connection, target)
        names = {
            row[0]
            for row in connection.execute(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"))
        }
        database_name = connection.execute(text("SELECT current_database()")).scalar_one()
    assert database_name == target["database"]
    assert "trg_team_config_version_guard" in names
    assert "trg_evaluation_revision_guard" in names
    yield engine, target
    engine.dispose()


def _seed(session):
    admin = User(
        id=uuid.uuid4(),
        full_name="pg-revision-admin",
        username=f"pg-revision-{uuid.uuid4().hex[:8]}",
        email=f"pg-revision-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="synthetic",
        role="Admin",
    )
    team = Team(id=uuid.uuid4(), name="Coding", db_name="Coding", display_name="Coding", region="UAE", team_level="employee")
    employee = Employee(id=uuid.uuid4(), employee_id=f"PG-{uuid.uuid4().hex[:8]}", name="Ada", team=team, region="UAE", performance_level="Employee")
    record = PerformanceRecord(
        id=uuid.uuid4(),
        year=2026,
        employee=employee,
        team=team,
        month="July",
        performance_level="Employee",
        position_name="",
        region="UAE",
        score=Decimal("70.00"),
        grade="D",
        status="Below",
        record_payload={"manager_notes": "keep July", "evaluation": {"score": 70.0, "grade": "D"}},
    )
    session.add_all([admin, team, employee, record])
    session.commit()
    actor = _actor(admin)
    workflow = EvaluationWorkflow(session)
    scope = next(
        item for item in workflow.sync_catalog(actor)["scopes"]
        if item["display_name"] == "Coding" and item["performance_level"] == "Employee" and item["position_name"] == ""
    )
    draft = workflow.open_draft(actor, scope["id"], 2026, 7)
    edited = workflow.edit_draft(actor, draft["id"], _line_edit(draft["lines"], 65))
    kpi = KPIValue(
        id=uuid.uuid4(),
        record_id=record.id,
        record_year=2026,
        kpi_key=edited["lines"][0]["kpi_key"],
        actual_value=Decimal("40"),
        target_value=Decimal("55"),
        achievement_ratio=Decimal("1"),
        weight_applied=Decimal("1"),
        contribution=Decimal("1"),
    )
    session.add(kpi)
    session.commit()
    workflow.impact_preview(actor, draft["id"])
    approved = workflow.approve(actor, draft["id"])
    session.refresh(record)
    return {
        "actor": actor,
        "scope_id": scope["id"],
        "version_id": approved["id"],
        "team_id": str(team.id),
        "record_id": str(record.id),
        "kpi_id": str(kpi.id),
        "score": record.score,
    }


def _session_call(engine, fn):
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        session.execute(text("SET statement_timeout = '12s'"))
        return fn(session)
    finally:
        session.close()


def test_stale_second_admin_checksum_is_refreshed_under_postgres_lock(pg):
    engine, _target = pg
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as first, factory() as second:
        seeded = _seed(first)
        admin_b = User(id=uuid.uuid4(), full_name="pg-stale-admin", username=f"pg-stale-{uuid.uuid4().hex[:8]}", email=f"pg-stale-{uuid.uuid4().hex[:8]}@example.com", password_hash="synthetic", role="Admin")
        first.add(admin_b)
        first.commit()
        actor_b = _actor(admin_b)
        workflow_a = EvaluationWorkflow(first)
        draft = workflow_a.revise(seeded["actor"], seeded["version_id"])
        # Keep a genuinely stale ORM identity in another independent session.
        cached = second.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
        assert cached.config_checksum == draft["checksum"]
        saved = workflow_a.edit_draft(seeded["actor"], draft["id"], _line_edit(draft["lines"], 70), expected_checksum=draft["checksum"], require_precondition=True)
        workflow_a.impact_preview(seeded["actor"], draft["id"])
        first.expire_all()
        current = first.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
        snapshot = copy.deepcopy(current.config_snapshot)
        assert "preview_evidence" in snapshot
        with pytest.raises(EvaluationConflict) as caught:
            EvaluationWorkflow(second).edit_draft(actor_b, draft["id"], _line_edit(draft["lines"], 80), expected_checksum=draft["checksum"], require_precondition=True)
        assert caught.value.data["code"] == "stale_draft"
        second.rollback()
        first.expire_all()
        preserved = first.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(draft["id"])).one()
        assert preserved.config_checksum == saved["checksum"]
        assert preserved.config_snapshot == snapshot


def test_guarded_workflow_locks_revision_apply_and_rollback(pg):
    engine, target = pg
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        seeded = _seed(session)
        actor = seeded["actor"]
        scope_id = seeded["scope_id"]
        version_id = seeded["version_id"]

        revise_results = {}

        def revise(name: str) -> None:
            def run(local):
                body = EvaluationWorkflow(local).revise(actor, version_id)
                revise_results[name] = body["id"]

            try:
                _session_call(engine, run)
            except Exception as exc:
                revise_results[name] = _describe(exc)

        revise_threads = [
            threading.Thread(target=revise, args=("left",), name="revise-left"),
            threading.Thread(target=revise, args=("right",), name="revise-right"),
        ]
        for thread in revise_threads:
            thread.start()
        _join(revise_threads)
        draft_ids = {value for value in revise_results.values() if isinstance(value, str) and "-" in value}
        assert len(draft_ids) == 1, revise_results
        assert session.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.status == "draft").count() == 1
        source = session.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == uuid.UUID(version_id)).one()
        assert source.status == "approved"
        draft_id = draft_ids.pop()

        EvaluationWorkflow(session).impact_preview(actor, draft_id)
        approve_results = {}

        def approve(name: str) -> None:
            def run(local):
                approve_results[name] = EvaluationWorkflow(local).approve(actor, draft_id)

            try:
                _session_call(engine, run)
            except Exception as exc:
                approve_results[name] = _describe(exc)

        approve_threads = [
            threading.Thread(target=approve, args=("left",), name="approve-left"),
            threading.Thread(target=approve, args=("right",), name="approve-right"),
        ]
        for thread in approve_threads:
            thread.start()
        _join(approve_threads)
        approved_bodies = [value for value in approve_results.values() if isinstance(value, dict)]
        denied = [value for value in approve_results.values() if isinstance(value, str)]
        assert len(approved_bodies) == 1, approve_results
        assert approved_bodies[0]["status"] == "approved"
        assert any(item.startswith("EvaluationError:immutable") for item in denied), approve_results
        session.expire_all()
        assert session.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.status == "approved").count() == 1
        current_id = approved_bodies[0]["id"]

        locked = threading.Event()
        mutated = threading.Event()
        started = threading.Event()
        finished = threading.Event()
        release = threading.Event()
        apply_result = {}

        def hold_team() -> None:
            with engine.connect() as connection:
                with connection.begin():
                    assert_safe(connection, target)
                    connection.execute(text("SET LOCAL statement_timeout = '12s'"))
                    connection.execute(text("SELECT id FROM teams WHERE id = :id FOR UPDATE"), {"id": seeded["team_id"]})
                    locked.set()
                    if not release.wait(20):
                        raise TimeoutError("team lock was not released")

        def mutate_actual() -> None:
            assert locked.wait(15)
            with engine.connect() as connection:
                assert_safe(connection, target)
                connection.execute(
                    text("UPDATE kpi_values SET actual_value = 1 WHERE id = :id"),
                    {"id": seeded["kpi_id"]},
                )
                connection.commit()
            mutated.set()

        def apply_while_locked() -> None:
            assert mutated.wait(15)
            started.set()

            def run(local):
                return EvaluationWorkflow(local).apply(actor, scope_id, 2026, 7)

            try:
                apply_result["body"] = _session_call(engine, run)
            except Exception as exc:
                apply_result["error"] = _describe(exc)
            finally:
                finished.set()

        holder = threading.Thread(target=hold_team, name="hold-team")
        mutator = threading.Thread(target=mutate_actual, name="mutate-actual")
        applier = threading.Thread(target=apply_while_locked, name="apply")
        holder.start()
        assert locked.wait(15)
        mutator.start()
        assert mutated.wait(15)
        applier.start()
        assert started.wait(15)
        threading.Event().wait(0.4)
        assert not finished.is_set()
        release.set()
        _join([holder, mutator, applier])
        assert apply_result.get("error") == "EvaluationConflict:stale_preview", apply_result
        session.expire_all()
        record = session.query(PerformanceRecord).filter(PerformanceRecord.id == uuid.UUID(seeded["record_id"])).one()
        assert record.score == seeded["score"]
        kpi = session.query(KPIValue).filter(KPIValue.id == uuid.UUID(seeded["kpi_id"])).one()
        kpi.actual_value = Decimal("40")
        session.commit()

        applied = EvaluationWorkflow(session).apply(actor, scope_id, 2026, 7)
        session.expire_all()
        record = session.query(PerformanceRecord).filter(PerformanceRecord.id == uuid.UUID(seeded["record_id"])).one()
        assert float(record.score) == round((40 / 65) * 100, 2)
        first = session.query(EvaluationRevision).filter(EvaluationRevision.id == uuid.UUID(applied["revision_id"])).one()
        assert first.status == "active"
        assert first.previous_revision_id is None

        revised = EvaluationWorkflow(session).revise(actor, current_id)
        EvaluationWorkflow(session).edit_draft(actor, revised["id"], _line_edit(revised["lines"], 80))
        EvaluationWorkflow(session).impact_preview(actor, revised["id"])
        EvaluationWorkflow(session).approve(actor, revised["id"])
        second_body = EvaluationWorkflow(session).apply(actor, scope_id, 2026, 7)
        session.expire_all()
        first = session.query(EvaluationRevision).filter(EvaluationRevision.id == first.id).one()
        second = session.query(EvaluationRevision).filter(EvaluationRevision.id == uuid.UUID(second_body["revision_id"])).one()
        assert first.status == "superseded"
        assert second.status == "active"
        assert second.previous_revision_id == first.id
        assert session.query(EvaluationRevision).filter(EvaluationRevision.status == "active").count() == 1

        record_locked = threading.Event()
        rollback_started = threading.Event()
        rollback_finished = threading.Event()
        release_record = threading.Event()
        rollback_result = {}

        def hold_record() -> None:
            with engine.connect() as connection:
                with connection.begin():
                    assert_safe(connection, target)
                    connection.execute(text("SET LOCAL statement_timeout = '12s'"))
                    connection.execute(
                        text("SELECT id FROM performance_records WHERE id = :id FOR UPDATE"),
                        {"id": seeded["record_id"]},
                    )
                    record_locked.set()
                    if not release_record.wait(20):
                        raise TimeoutError("record lock was not released")

        def rollback_while_locked() -> None:
            assert record_locked.wait(15)
            rollback_started.set()

            def run(local):
                return EvaluationWorkflow(local).rollback(actor, second_body["revision_id"])

            try:
                rollback_result["body"] = _session_call(engine, run)
            except Exception as exc:
                rollback_result["error"] = _describe(exc)
            finally:
                rollback_finished.set()

        record_holder = threading.Thread(target=hold_record, name="hold-record")
        rollback_thread = threading.Thread(target=rollback_while_locked, name="rollback")
        record_holder.start()
        assert record_locked.wait(15)
        rollback_thread.start()
        assert rollback_started.wait(15)
        threading.Event().wait(0.4)
        assert not rollback_finished.is_set()
        release_record.set()
        _join([record_holder, rollback_thread])
        assert rollback_result.get("body", {}).get("status") == "rolled_back", rollback_result
        session.expire_all()
        first = session.query(EvaluationRevision).filter(EvaluationRevision.id == first.id).one()
        second = session.query(EvaluationRevision).filter(EvaluationRevision.id == second.id).one()
        record = session.query(PerformanceRecord).filter(PerformanceRecord.id == uuid.UUID(seeded["record_id"])).one()
        assert first.status == "superseded"
        assert second.status == "rolled_back"
        assert float(record.score) == round((40 / 65) * 100, 2)
        with pytest.raises(EvaluationError) as repeated:
            EvaluationWorkflow(session).rollback(actor, second_body["revision_id"])
        assert repeated.value.data["code"] == "immutable"
        session.rollback()
        session.expire_all()
        assert session.query(EvaluationRevision).filter(EvaluationRevision.id == second.id).one().status == "rolled_back"
        assert float(session.query(PerformanceRecord).filter(PerformanceRecord.id == uuid.UUID(seeded["record_id"])).one().score) == round((40 / 65) * 100, 2)

        with pytest.raises(EvaluationConflict) as older:
            EvaluationWorkflow(session).rollback(actor, str(first.id))
        assert older.value.data["code"] == "not_latest"
        session.rollback()

        third_body = EvaluationWorkflow(session).apply(actor, scope_id, 2026, 7)
        session.expire_all()
        third = session.query(EvaluationRevision).filter(EvaluationRevision.id == uuid.UUID(third_body["revision_id"])).one()
        assert third.status == "active"
        assert third.previous_revision_id == second.id
        assert session.query(EvaluationRevision).filter(EvaluationRevision.id == second.id).one().status == "rolled_back"
        assert session.query(EvaluationRevision).filter(EvaluationRevision.id == first.id).one().status == "superseded"
        assert session.query(EvaluationRevision).filter(EvaluationRevision.status == "active").count() == 1
    finally:
        session.close()
