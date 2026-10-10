"""Opt-in PostgreSQL 16/18 overlap checks for the dormant outbox publisher.

This module is not named test_*.py, so a normal pytest collection does not
run it or reset a database. A reviewer runs it by path, one process at a
time, after other disposable-database work has stopped:

    python -X utf8 -m pytest -q -p no:cacheprovider tests/evaluation_outbox_publisher_pg_checks.py

The runner must already have APP_ENV=test, DATABASE_URL=sqlite:///:memory:,
and an empty REDIS_URL. Import does not connect, reset, or create containers.
Owned URLs are the disposable loopback pair from evaluation_history_pg_checks.
This slice does not execute this module.
"""

from __future__ import annotations

import importlib.util
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

if os.environ.get("APP_ENV") != "test" or os.environ.get("DATABASE_URL") != "sqlite:///:memory:":
    raise RuntimeError(
        "evaluation_outbox_publisher_pg_checks requires APP_ENV=test and "
        "DATABASE_URL=sqlite:///:memory: from the runner before import. "
        "Owned PostgreSQL URLs are applied only for allowlisted connections."
    )
if os.environ.get("REDIS_URL", "") != "":
    raise RuntimeError("evaluation_outbox_publisher_pg_checks refuses a non-empty REDIS_URL.")

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import sessionmaker

from models.models import CacheInvalidationOutbox, PerformanceRecord
from services.evaluation.outbox_publisher import (
    DATA_VERSION_KEY,
    DELIVERY_ERRORS,
    FAULT_AFTER_PUBLISH_BEFORE_ACK,
    FAULT_BEFORE_ACK_COMMIT,
    FAULT_INFO_KEY,
    INVALIDATION_CHANNEL,
    LOCK_INFO_KEY,
    CacheOutboxPublisher,
    OutboxDeliveryError,
    version_bump_message,
)
from services.evaluation.workflow import EvaluationWorkflow


def _load(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FOUNDATION = _load("evaluation_apply_foundation_pg_checks.py", "evaluation_apply_foundation_pg_checks_for_outbox")
_CHARACTER = _load("test_evaluation_bounded_apply.py", "bounded_apply_sqlite_characterization_for_outbox")

pg = _FOUNDATION.pg
assert_public_search_path = _FOUNDATION.assert_public_search_path

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
PARENT_PROBES = (
    "SELECT id FROM processing_jobs FOR UPDATE",
    "SELECT id FROM evaluation_scopes FOR UPDATE",
    "SELECT job_id FROM evaluation_apply_controls FOR UPDATE",
    "SELECT id, year FROM performance_records FOR UPDATE",
    "SELECT id FROM teams FOR UPDATE",
)


def _session(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _promote(engine):
    Session = _session(engine)
    with Session() as session:
        session.execute(text("SET statement_timeout = '20s'"))
        world, scope = _CHARACTER._bulk_coding(session, 1)
        captured = world.service.capture(world.actor, scope["id"], 2026, 7)
        _CHARACTER._stage_all(world.service, world.actor, captured["job_id"], 1)
        world.service.promote(world.actor, captured["job_id"])
    with Session() as other:
        row = other.query(CacheInvalidationOutbox).one()
        assert row.published_at is None
        assert row.delivery_attempts == 0
        scores = tuple(
            (str(record.id), str(record.score), record.grade)
            for record in other.query(PerformanceRecord).order_by(PerformanceRecord.id).all()
        )
    return scores


class _Client:
    def __init__(self):
        self.calls = []
        self.version = 0
        self.publish_error = None
        self._lock = threading.Lock()

    def __bool__(self):
        raise AssertionError("client truthiness")

    def incr(self, key):
        with self._lock:
            self.version += 1
            current = self.version
            self.calls.append(("incr", key))
        if key != DATA_VERSION_KEY:
            raise AssertionError(key)
        return current

    def publish(self, channel, message):
        with self._lock:
            self.calls.append(("publish", channel, message))
            error = self.publish_error
            if error is not None:
                self.publish_error = None
                raise error
        if channel != INVALIDATION_CHANNEL:
            raise AssertionError(channel)
        return 0

    def delete(self, *args, **kwargs):
        raise AssertionError("delete")


def test_two_publishers_skip_the_locked_row_and_do_not_lock_parents(pg, monkeypatch):
    """One connection holds the outbox row. The other must not acknowledge it."""

    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda self, kind: None)
    engine, target = pg
    with engine.connect() as connection:
        assert_public_search_path(connection, target)
    scores = _promote(engine)
    Session = _session(engine)
    client = _Client()
    locked = threading.Event()
    release = threading.Event()
    outcomes = {}
    sql = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "cache_invalidation_outbox" in statement.lower():
            sql.append(statement)

    def hold(ids):
        outcomes["locked_ids"] = tuple(str(item) for item in ids)
        outcomes["lock_sql"] = list(sql)
        locked.set()
        assert release.wait(20), "outbox lock was not released"

    def run_holder():
        try:
            with Session() as session:
                session.execute(text("SET statement_timeout = '30s'"))
                event.listen(session.get_bind(), "before_cursor_execute", capture)
                try:
                    session.info[LOCK_INFO_KEY] = hold
                    outcomes["holder"] = CacheOutboxPublisher(
                        session,
                        client,
                        clock=lambda: NOW,
                    ).deliver_due(enabled=True, limit=1)
                finally:
                    event.remove(session.get_bind(), "before_cursor_execute", capture)
        except Exception as exc:
            outcomes["holder_error"] = repr(exc)
        finally:
            locked.set()

    holder = threading.Thread(target=run_holder, name="outbox-holder")
    holder.start()
    try:
        assert locked.wait(20), outcomes
        assert "holder_error" not in outcomes, outcomes
        assert outcomes["locked_ids"], outcomes
        rendered = "\n".join(outcomes["lock_sql"]).lower()
        assert "for update" in rendered
        assert "skip locked" in rendered
        assert "cache_invalidation_outbox" in rendered
        for forbidden in ("performance_records", "processing_jobs", "evaluation_apply_controls", "teams"):
            assert forbidden not in rendered
        with engine.connect() as connection:
            assert_public_search_path(connection, target)
            connection.execute(text("SELECT pg_stat_clear_snapshot()"))
            modes = connection.execute(text(
                """
                SELECT lock.mode
                FROM pg_locks lock
                JOIN pg_class class ON class.oid = lock.relation
                WHERE class.relname = 'cache_invalidation_outbox'
                  AND lock.granted
                  AND lock.locktype = 'relation'
                """
            )).scalars().all()
            assert "RowShareLock" in modes
        with Session() as probe:
            probe.execute(text("SET statement_timeout = '3s'"))
            probe.execute(text("SET lock_timeout = '3s'"))
            for statement in PARENT_PROBES:
                probe.execute(text(statement))
            probe.rollback()
        with Session() as other:
            other.execute(text("SET statement_timeout = '5s'"))
            other.execute(text("SET lock_timeout = '3s'"))
            outcomes["other"] = CacheOutboxPublisher(
                other,
                client,
                clock=lambda: NOW,
            ).deliver_due(enabled=True, limit=1)
        assert outcomes["other"] == {
            "enabled": True,
            "considered": 0,
            "published": 0,
            "failed": 0,
        }
        assert client.version == 0
        assert client.calls == []
    finally:
        release.set()
        holder.join(20)

    assert not holder.is_alive()
    assert outcomes.get("holder") == {
        "enabled": True,
        "considered": 1,
        "published": 1,
        "failed": 0,
    }, outcomes
    assert client.version == 1
    assert client.calls == [
        ("incr", DATA_VERSION_KEY),
        ("publish", INVALIDATION_CHANNEL, version_bump_message(1)),
    ]
    with Session() as other:
        row = other.query(CacheInvalidationOutbox).one()
        assert row.published_at is not None
        assert row.delivery_attempts == 1
        assert row.last_error is None
        assert row.next_retry_at is None
        seen = tuple(
            (str(record.id), str(record.score), record.grade)
            for record in other.query(PerformanceRecord).order_by(PerformanceRecord.id).all()
        )
        assert seen == scores
        assert other.query(CacheInvalidationOutbox).count() == 1


def test_failure_commits_and_crash_before_ack_retries_with_another_increment(pg, monkeypatch):
    """A publish error stays unpublished. A crash after Redis does not ack."""

    monkeypatch.setattr(EvaluationWorkflow, "_bump", lambda self, kind: None)
    engine, target = pg
    with engine.connect() as connection:
        assert_public_search_path(connection, target)
    scores = _promote(engine)
    Session = _session(engine)
    client = _Client()
    sentinel = "Outbox Sentinel score 100 Coding manager_notes"
    client.publish_error = ConnectionError(sentinel)
    cell = {"now": NOW}
    with Session() as session:
        session.execute(text("SET statement_timeout = '20s'"))
        summary = CacheOutboxPublisher(session, client, clock=lambda: cell["now"]).deliver_due(
            enabled=True,
            limit=1,
        )
    assert summary["published"] == 0
    assert summary["failed"] == 1
    assert client.version == 1
    with Session() as other:
        row = other.query(CacheInvalidationOutbox).one()
        assert row.published_at is None
        assert row.delivery_attempts == 1
        assert row.last_error == DELIVERY_ERRORS["publish_failed"]
        assert sentinel not in row.last_error
        due = row.next_retry_at
        assert due is not None
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        assert due - NOW == timedelta(seconds=30)
        original = (
            str(row.id),
            str(row.job_id),
            str(row.revision_id),
            row.namespace,
            row.dedup_key,
            row.created_at,
            int(row.delivery_attempts),
        )

    cell["now"] = due
    with Session() as session:
        session.execute(text("SET statement_timeout = '20s'"))
        session.info[FAULT_INFO_KEY] = FAULT_AFTER_PUBLISH_BEFORE_ACK
        with pytest.raises(OutboxDeliveryError) as crashed:
            CacheOutboxPublisher(session, client, clock=lambda: cell["now"]).deliver_due(
                enabled=True,
                limit=1,
            )
        assert crashed.value.code == "acknowledgment_failed"
    assert client.version == 2
    with Session() as other:
        row = other.query(CacheInvalidationOutbox).one()
        assert row.published_at is None
        assert int(row.delivery_attempts) == 1
        assert (
            str(row.id),
            str(row.job_id),
            str(row.revision_id),
            row.namespace,
            row.dedup_key,
            row.created_at,
            int(row.delivery_attempts),
        ) == original

    with Session() as session:
        session.execute(text("SET statement_timeout = '20s'"))
        session.info[FAULT_INFO_KEY] = FAULT_BEFORE_ACK_COMMIT
        with pytest.raises(OutboxDeliveryError) as flushed:
            CacheOutboxPublisher(session, client, clock=lambda: cell["now"]).deliver_due(
                enabled=True,
                limit=1,
            )
        assert flushed.value.code == "acknowledgment_failed"
    assert client.version == 3
    with Session() as other:
        row = other.query(CacheInvalidationOutbox).one()
        assert row.published_at is None
        assert int(row.delivery_attempts) == 1

    with Session() as session:
        session.execute(text("SET statement_timeout = '20s'"))
        summary = CacheOutboxPublisher(session, client, clock=lambda: cell["now"]).deliver_due(
            enabled=True,
            limit=1,
        )
    assert summary["published"] == 1
    assert client.version == 4
    assert client.calls[-1] == ("publish", INVALIDATION_CHANNEL, version_bump_message(4))
    with Session() as other:
        row = other.query(CacheInvalidationOutbox).one()
        assert row.published_at is not None
        assert int(row.delivery_attempts) == 2
        assert row.last_error is None
        assert row.next_retry_at is None
        assert str(row.id) == original[0]
        assert str(row.job_id) == original[1]
        assert str(row.revision_id) == original[2]
        assert row.namespace == original[3]
        assert row.dedup_key == original[4]
        seen = tuple(
            (str(record.id), str(record.score), record.grade)
            for record in other.query(PerformanceRecord).order_by(PerformanceRecord.id).all()
        )
        assert seen == scores
        assert other.query(CacheInvalidationOutbox).count() == 1
    with Session() as session:
        session.execute(text("SET statement_timeout = '20s'"))
        idle = CacheOutboxPublisher(session, client, clock=lambda: cell["now"]).deliver_due(
            enabled=True,
            limit=1,
        )
    assert idle["published"] == 0
    assert idle["considered"] == 0
    assert client.version == 4
