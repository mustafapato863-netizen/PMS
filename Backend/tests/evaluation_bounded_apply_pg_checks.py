"""Opt-in PostgreSQL 16/18 crash and race checks for dormant bounded apply.

This module is not named test_*.py, so a normal pytest collection does not
run it or reset a database. A reviewer runs it by path, one process at a
time, after the delegate has stopped:

    python -X utf8 -m pytest -q -p no:cacheprovider tests/evaluation_bounded_apply_pg_checks.py

The runner must already have APP_ENV=test, DATABASE_URL=sqlite:///:memory:,
and an empty REDIS_URL. Import does not connect, reset, or create containers.
Owned URLs are the disposable loopback pair from evaluation_history_pg_checks.
"""

from __future__ import annotations

import importlib.util
import os
import threading
import time
import uuid
from pathlib import Path

if os.environ.get("APP_ENV") != "test" or os.environ.get("DATABASE_URL") != "sqlite:///:memory:":
    raise RuntimeError(
        "evaluation_bounded_apply_pg_checks requires APP_ENV=test and "
        "DATABASE_URL=sqlite:///:memory: from the runner before import. "
        "Owned PostgreSQL URLs are applied only for allowlisted connections."
    )
if os.environ.get("REDIS_URL", "") != "":
    raise RuntimeError("evaluation_bounded_apply_pg_checks refuses a non-empty REDIS_URL.")

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from models.models import (
    CacheInvalidationOutbox,
    EvaluationApplyControl,
    EvaluationApplyStageRow,
    EvaluationRevision,
    PerformanceRecord,
    ProcessingJob,
    User,
)
from services.evaluation.access import AccessDenied
from services.evaluation.bounded_apply import FAULT_POINTS, BoundedApplyService
from services.evaluation.resolver import lock_team_rows
from services.evaluation.workflow import EvaluationConflict, EvaluationWorkflow


def _load(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FOUNDATION = _load("evaluation_apply_foundation_pg_checks.py", "evaluation_apply_foundation_pg_checks")
_CHARACTER = _load("test_evaluation_bounded_apply.py", "bounded_apply_sqlite_characterization")

pg = _FOUNDATION.pg
assert_public_search_path = _FOUNDATION.assert_public_search_path
TARGETS = _FOUNDATION.TARGETS


def _session(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _scores(session) -> tuple:
    return tuple(
        (str(row.id), int(row.year), str(row.score), row.grade)
        for row in session.query(PerformanceRecord).order_by(PerformanceRecord.year, PerformanceRecord.id).all()
    )


def test_faults_and_stale_epoch_leave_before_or_one_committed_result(pg, monkeypatch):
    """A second connection sees the pre-promote image, then exactly one revision and outbox."""
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda self, kind: None)
    engine, target = pg
    Session = _session(engine)
    with engine.connect() as connection:
        assert_public_search_path(connection, target)
    with Session() as session:
        session.execute(text("SET statement_timeout = '20s'"))
        world, scope = _CHARACTER._bulk_coding(session, 2)
        captured = world.service.capture(world.actor, scope["id"], 2026, 7)
        _CHARACTER._stage_all(world.service, world.actor, captured["job_id"], 2)
        actor = world.actor
        job_id = captured["job_id"]
        before = _scores(session)
    with Session() as session:
        session.execute(text("SET statement_timeout = '20s'"))
        with pytest.raises(EvaluationConflict) as stale:
            BoundedApplyService(session).promote(actor, job_id, expected_epoch=9)
        assert stale.value.data["code"] == "stale_epoch"
    with Session() as other:
        assert _scores(other) == before
        assert other.query(EvaluationRevision).count() == 0
        assert other.query(CacheInvalidationOutbox).count() == 0
        assert other.query(EvaluationApplyControl).one().state == "staging"
    for point in FAULT_POINTS:
        with Session() as session:
            session.execute(text("SET statement_timeout = '20s'"))
            session.info["bounded_apply_fault"] = point
            with pytest.raises(EvaluationConflict) as faulted:
                BoundedApplyService(session).promote(actor, job_id, expected_epoch=0)
            assert faulted.value.data["code"] == "fault_injected"
        with Session() as other:
            assert _scores(other) == before
            control = other.query(EvaluationApplyControl).one()
            assert control.state == "staging"
            assert control.promoted_revision_id is None
            assert control.promoted_count == 0
            assert other.query(EvaluationRevision).count() == 0
            assert other.query(CacheInvalidationOutbox).count() == 0
    with Session() as session:
        session.execute(text("SET statement_timeout = '20s'"))
        promoted = BoundedApplyService(session).promote(actor, job_id, expected_epoch=0)
        repeated = BoundedApplyService(session).promote(actor, job_id, expected_epoch=4)
        assert repeated["idempotent"] is True
        assert repeated["revision_id"] == promoted["revision_id"]
    with Session() as other:
        assert other.query(EvaluationRevision).count() == 1
        outbox = other.query(CacheInvalidationOutbox).one()
        assert outbox.published_at is None
        assert outbox.delivery_attempts == 0
        assert outbox.revision_id == uuid.UUID(promoted["revision_id"])
        assert other.query(PerformanceRecord).filter(PerformanceRecord.grade == "A").count() == 2
        assert other.query(EvaluationApplyControl).one().state == "promoted"


def test_team_lock_serializes_promote_and_rollback(pg, monkeypatch):
    """Upload's team-row lock and a later rollback share one lock order with promotion."""
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda self, kind: None)
    engine, target = pg
    Session = _session(engine)
    with Session() as session:
        world, scope = _CHARACTER._bulk_coding(session, 1)
        captured = world.service.capture(world.actor, scope["id"], 2026, 7)
        _CHARACTER._stage_all(world.service, world.actor, captured["job_id"], 1)
        actor = world.actor
        job_id = captured["job_id"]
        team_id = world.teams["Coding"].id
        before = _scores(session)

    held = threading.Event()
    release = threading.Event()
    started = threading.Event()
    finished = threading.Event()
    outcomes = {}

    def hold_teams():
        try:
            with Session() as session:
                session.execute(text("SET statement_timeout = '20s'"))
                lock_team_rows(session, [team_id])
                held.set()
                assert release.wait(20), "team lock was not released"
                session.rollback()
                outcomes["holder"] = "released"
        except Exception as exc:
            outcomes["holder_error"] = repr(exc)
            held.set()

    def promote():
        try:
            with Session() as session:
                session.execute(text("SET statement_timeout = '20s'"))
                started.set()
                outcomes["promote"] = BoundedApplyService(session).promote(actor, job_id)
        except Exception as exc:
            outcomes["promote_error"] = repr(exc)
        finally:
            finished.set()

    holder = threading.Thread(target=hold_teams, name="bounded-team-lock")
    worker = threading.Thread(target=promote, name="bounded-promote")
    holder.start()
    try:
        assert held.wait(15), outcomes
        assert "holder_error" not in outcomes, outcomes
        worker.start()
        assert started.wait(15), outcomes
        with engine.connect() as connection:
            assert_public_search_path(connection, target)
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
                assert time.monotonic() < deadline, "promote did not wait on the team lock"
                threading.Event().wait(0.05)
        assert not finished.is_set(), outcomes
    finally:
        release.set()
        holder.join(20)
        worker.join(20)

    assert outcomes.get("holder") == "released", outcomes
    assert outcomes.get("promote", {}).get("applied_count") == 1, outcomes
    with Session() as other:
        assert other.query(EvaluationRevision).count() == 1
        assert other.query(CacheInvalidationOutbox).count() == 1
        revision_id = other.query(EvaluationRevision).one().id
        assert _scores(other) != before

    release.clear()
    held.clear()
    finished.clear()
    started.clear()
    outcomes.clear()

    def roll_back():
        try:
            with Session() as session:
                session.execute(text("SET statement_timeout = '20s'"))
                started.set()
                outcomes["rollback"] = BoundedApplyService(session).rollback_latest(actor, revision_id)
        except Exception as exc:
            outcomes["rollback_error"] = repr(exc)
        finally:
            finished.set()

    holder = threading.Thread(target=hold_teams, name="bounded-team-lock-rollback")
    worker = threading.Thread(target=roll_back, name="bounded-rollback")
    holder.start()
    try:
        assert held.wait(15), outcomes
        worker.start()
        assert started.wait(15), outcomes
        with engine.connect() as connection:
            assert_public_search_path(connection, target)
            deadline = time.monotonic() + 5
            while True:
                connection.execute(text("SELECT pg_stat_clear_snapshot()"))
                blocked = connection.execute(text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )).scalar_one()
                if blocked:
                    break
                assert not finished.is_set(), outcomes
                assert time.monotonic() < deadline, "rollback did not wait on the team lock"
                threading.Event().wait(0.05)
    finally:
        release.set()
        holder.join(20)
        worker.join(20)

    assert outcomes.get("rollback", {}).get("status") == "rolled_back", outcomes
    with Session() as other:
        assert _scores(other) == before
        revision = other.query(EvaluationRevision).one()
        assert revision.status == "rolled_back"
        assert other.query(EvaluationRevision).filter(EvaluationRevision.status == "active").count() == 0
        assert other.query(CacheInvalidationOutbox).count() == 1


def test_mixed_uuid_identity_and_one_promote_winner(pg, monkeypatch):
    """Native UUID order matches str(id), and two promoters leave one revision."""
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda self, kind: None)
    engine, target = pg
    Session = _session(engine)
    chosen = [
        uuid.UUID(int=1),
        uuid.UUID(int=2**100),
        uuid.uuid4(),
        uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
    ]
    with Session() as session:
        with engine.connect() as connection:
            assert_public_search_path(connection, target)
        world = _CHARACTER._World(session)
        scope = world.scope("Coding")
        draft = world.ratio_draft(scope["id"], 7, 50)
        key = draft["lines"][0]["kpi_key"]
        team = world.teams["Coding"]
        upload = world.upload_for(team, "July")
        employee = world.employee(team, "C-mix", "Mixed")
        shared = chosen[0]
        for record_id in chosen:
            record = world.record(employee, "July", "70.00", "D", record_id=record_id, upload=upload)
            world.kpi(record, key, "60", "40")
        older = world.record(employee, "July", "12.00", "E", record_id=shared, year=2025, upload=upload)
        world.kpi(older, key, "60", "40")
        session.commit()
        _CHARACTER._approve(world.workflow, world.actor, draft["id"])
        captured = world.service.capture(world.actor, scope["id"], 2026, 7)
        _CHARACTER._stage_all(world.service, world.actor, captured["job_id"], len(chosen), page_size=1)
        staged = [
            str(row.record_id)
            for row in session.query(EvaluationApplyStageRow)
            .order_by(EvaluationApplyStageRow.record_year, EvaluationApplyStageRow.record_id)
            .all()
        ]
        assert staged == sorted(str(value) for value in chosen)
        assert session.query(EvaluationApplyStageRow).filter(EvaluationApplyStageRow.record_year == 2025).count() == 0
        actor = world.actor
        job_id = captured["job_id"]

    outcomes = {}
    barrier = threading.Barrier(2)

    def promote(name: str):
        try:
            barrier.wait(15)
            with Session() as session:
                session.execute(text("SET statement_timeout = '20s'"))
                outcomes[name] = BoundedApplyService(session).promote(actor, job_id)
        except Exception as exc:
            outcomes[name] = exc

    threads = [threading.Thread(target=promote, args=(name,)) for name in ("left", "right")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    successes = [value for value in outcomes.values() if isinstance(value, dict)]
    failures = [value for value in outcomes.values() if isinstance(value, Exception)]
    assert len(successes) >= 1, outcomes
    for failure in failures:
        assert getattr(failure, "data", {}).get("code") in {"duplicate_binding", "invalid_state", "evidence_changed"}, outcomes
    with Session() as other:
        assert other.query(EvaluationRevision).count() == 1
        assert other.query(CacheInvalidationOutbox).count() == 1
        assert other.query(PerformanceRecord).filter(PerformanceRecord.year == 2026, PerformanceRecord.grade == "A").count() == len(chosen)
        older_row = other.query(PerformanceRecord).filter(PerformanceRecord.year == 2025).one()
        assert older_row.score == __import__("decimal").Decimal("12.00")
        assert other.query(EvaluationRevision).one().status == "active"


def test_existing_capture_and_stage_do_not_deadlock(pg, monkeypatch):
    """Capture holds the team fence before control. Stage waits there, then both finish.

    Equivalent to the two-connection probe: pause an existing capture after the
    team fence and before its control lock; the stage must not already hold
    that control. Do not retry a deadlock and do not drop this ordering.
    """
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda *args: None)
    engine, target = pg
    Session = _session(engine)
    with engine.connect() as connection:
        assert_public_search_path(connection, target)
    with Session() as session:
        world, scope = _CHARACTER._bulk_coding(session, 1)
        captured = world.service.capture(world.actor, scope["id"], 2026, 7)
        actor = world.actor
        job_id = captured["job_id"]
    held = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    results = {}

    def capture_again():
        try:
            with Session() as session:
                session.execute(text("SET statement_timeout = '12s'"))
                service = BoundedApplyService(session)
                original = service._lock_query
                paused = [False]

                def stop_before_existing_control(query, lock):
                    entity = query.column_descriptions[0].get("entity")
                    if lock and entity is EvaluationApplyControl and not paused[0]:
                        paused[0] = True
                        held.set()
                        assert release.wait(10), "capture fixture not released"
                    return original(query, lock)

                service._lock_query = stop_before_existing_control
                results["capture"] = service.capture(actor, scope["id"], 2026, 7)
        except Exception as error:
            results["capture_error"] = repr(error)
            held.set()

    def stage():
        try:
            with Session() as session:
                session.execute(text("SET statement_timeout = '12s'"))
                results["stage"] = BoundedApplyService(session).stage_page(actor, job_id, expected_epoch=0)
        except Exception as error:
            results["stage_error"] = repr(error)
        finally:
            finished.set()

    owner = threading.Thread(target=capture_again, name="bounded-capture-overlap")
    worker = threading.Thread(target=stage, name="bounded-stage-overlap")
    owner.start()
    try:
        assert held.wait(10), results
        assert "capture_error" not in results, results
        worker.start()
        with engine.connect() as connection:
            assert_public_search_path(connection, target)
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
                assert not finished.is_set(), results
                assert time.monotonic() < deadline, "stage did not wait on capture's team fence"
                threading.Event().wait(0.05)
    finally:
        release.set()
        owner.join(15)
        if worker.ident is not None:
            worker.join(15)
    assert not owner.is_alive() and not worker.is_alive(), results
    assert "capture_error" not in results and "stage_error" not in results, results
    assert results["capture"]["job_id"] == job_id and results["capture"]["resumed"] is True, results
    assert results["stage"]["inserted_count"] == 1, results
    with Session() as session:
        assert session.query(EvaluationApplyStageRow).count() == 1
        assert session.query(EvaluationApplyControl).one().state == "staging"


def _revoke_while_team_fence_is_held(engine, target, team_id, actor, invoke) -> dict:
    """Commit a role change only after pg_stat_activity shows the team-lock wait."""
    Session = _session(engine)
    result = {}
    finished = threading.Event()
    started = False

    def worker():
        try:
            with Session() as db:
                db.execute(text("SET statement_timeout = '12s'"))
                invoke(db)
        except Exception as error:
            result["error"] = error
        finally:
            finished.set()

    thread = threading.Thread(target=worker, name="bounded-role-revocation")
    with Session() as fence:
        assert_public_search_path(fence.connection(), target)
        lock_team_rows(fence, [team_id])
        thread.start()
        started = True
        try:
            with engine.connect() as observer:
                assert_public_search_path(observer, target)
                deadline = time.monotonic() + 5
                while True:
                    observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                    blocked = observer.execute(text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND wait_event_type = 'Lock' "
                        "AND query ILIKE '%teams%'"
                    )).scalar_one()
                    if blocked:
                        break
                    assert not finished.is_set(), result
                    assert time.monotonic() < deadline, "operation did not wait on the team fence"
                    threading.Event().wait(0.05)
            with Session() as revoker:
                assert_public_search_path(revoker.connection(), target)
                updated = revoker.query(User).filter(User.id == uuid.UUID(actor["user_id"])).update(
                    {User.role: "Performance Team"},
                    synchronize_session=False,
                )
                assert updated == 1
                revoker.commit()
        finally:
            fence.rollback()
            if started:
                thread.join(15)
    assert not thread.is_alive(), result
    assert isinstance(result.get("error"), AccessDenied), result
    with Session() as checker:
        assert checker.query(User.role).filter(User.id == uuid.UUID(actor["user_id"])).scalar() == "Performance Team"
        restored = checker.query(User).filter(User.id == uuid.UUID(actor["user_id"])).update(
            {User.role: "Admin", User.is_active: True},
            synchronize_session=False,
        )
        assert restored == 1
        checker.commit()
    return result


def test_role_revoked_during_team_fence_cannot_mutate(pg, monkeypatch):
    """Capture resume, stage, promote, completed replay, and rollback reread Admin.

    The second connection commits the role change while pg_stat_activity shows
    the team-lock wait. The users row is not locked, so this does not prove a
    revocation that commits after the post-fence read is serialized.
    """
    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda *args: None)
    engine, target = pg
    Session = _session(engine)
    with engine.connect() as connection:
        assert_public_search_path(connection, target)
    with Session() as session:
        session.execute(text("SET statement_timeout = '20s'"))
        world, scope = _CHARACTER._bulk_coding(session, 1)
        captured = world.service.capture(world.actor, scope["id"], 2026, 7)
        actor = dict(world.actor)
        job_id = captured["job_id"]
        scope_id = scope["id"]
        team_id = world.teams["Coding"].id
        before = _scores(session)
        assert session.query(EvaluationApplyControl).one().actor_snapshot["role"] == "Admin"

    _revoke_while_team_fence_is_held(
        engine,
        target,
        team_id,
        actor,
        lambda db: BoundedApplyService(db).capture(actor, scope_id, 2026, 7),
    )
    with Session() as session:
        assert _scores(session) == before
        assert session.query(ProcessingJob).count() == 1
        assert session.query(EvaluationApplyControl).one().state == "staging"
        assert session.query(EvaluationApplyControl).one().actor_snapshot["role"] == "Admin"
        assert session.query(EvaluationApplyStageRow).count() == 0
        assert session.query(EvaluationRevision).count() == 0
        assert session.query(CacheInvalidationOutbox).count() == 0

    _revoke_while_team_fence_is_held(
        engine,
        target,
        team_id,
        actor,
        lambda db: BoundedApplyService(db).stage_page(actor, job_id, expected_epoch=0),
    )
    with Session() as session:
        assert _scores(session) == before
        assert session.query(EvaluationApplyControl).one().state == "staging"
        assert session.query(EvaluationApplyStageRow).count() == 0
        assert session.query(EvaluationRevision).count() == 0
        assert session.query(CacheInvalidationOutbox).count() == 0

    with Session() as session:
        session.execute(text("SET statement_timeout = '20s'"))
        staged = BoundedApplyService(session).stage_page(actor, job_id, expected_epoch=0)
        assert staged["inserted_count"] == 1

    _revoke_while_team_fence_is_held(
        engine,
        target,
        team_id,
        actor,
        lambda db: BoundedApplyService(db).promote(actor, job_id, expected_epoch=0),
    )
    with Session() as session:
        assert _scores(session) == before
        assert session.query(EvaluationApplyControl).one().state == "staging"
        assert session.query(EvaluationApplyStageRow).count() == 1
        assert session.query(EvaluationRevision).count() == 0
        assert session.query(CacheInvalidationOutbox).count() == 0

    with Session() as session:
        session.execute(text("SET statement_timeout = '20s'"))
        promoted = BoundedApplyService(session).promote(actor, job_id, expected_epoch=0)
        assert promoted["idempotent"] is False
        revision_id = promoted["revision_id"]
        promoted_scores = _scores(session)
        assert session.query(EvaluationRevision).one().status == "active"
        assert session.query(CacheInvalidationOutbox).count() == 1

    _revoke_while_team_fence_is_held(
        engine,
        target,
        team_id,
        actor,
        lambda db: BoundedApplyService(db).promote(actor, job_id, expected_epoch=8),
    )
    with Session() as session:
        assert _scores(session) == promoted_scores
        assert session.query(EvaluationRevision).count() == 1
        assert session.query(EvaluationRevision).one().status == "active"
        assert session.query(CacheInvalidationOutbox).count() == 1
        replay = BoundedApplyService(session).promote(actor, job_id, expected_epoch=8)
        assert replay["idempotent"] is True
        assert replay["revision_id"] == revision_id
        assert _scores(session) == promoted_scores
        assert session.query(EvaluationRevision).count() == 1
        assert session.query(CacheInvalidationOutbox).count() == 1

    _revoke_while_team_fence_is_held(
        engine,
        target,
        team_id,
        actor,
        lambda db: BoundedApplyService(db).rollback_latest(actor, revision_id),
    )
    with Session() as session:
        assert _scores(session) == promoted_scores
        revision = session.query(EvaluationRevision).one()
        assert revision.status == "active"
        assert session.query(CacheInvalidationOutbox).count() == 1
        assert session.query(EvaluationApplyControl).one().actor_snapshot["role"] == "Admin"
        assert session.query(EvaluationApplyControl).one().requested_by_user_id == uuid.UUID(actor["user_id"])
