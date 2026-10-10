"""SQLite characterization for the dormant cache outbox publisher.

The service is not registered with a worker, a setting, or a route. These
tests reuse the anonymous bounded-apply fixture and read the outbox rows
back from the database. They do not open PostgreSQL or Redis.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import logging
import os
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

if (
    os.environ.get("APP_ENV") != "test"
    or os.environ.get("DATABASE_URL") != "sqlite:///:memory:"
    or os.environ.get("REDIS_URL", "")
):
    raise RuntimeError("Anonymous environment required before imports")

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql

from models.models import (
    CacheInvalidationOutbox,
    EvaluationApplyControl,
    PerformanceRecord,
    Team,
    User,
)
from services.cache_invalidation_service import _fallback_data_version
import services.evaluation.outbox_publisher as publisher_module
from services.evaluation.outbox_publisher import (
    DATA_VERSION_KEY,
    DEFAULT_BATCH_LIMIT,
    DELIVERY_ERRORS,
    FAULT_AFTER_PUBLISH_BEFORE_ACK,
    FAULT_BEFORE_ACK_COMMIT,
    FAULT_INFO_KEY,
    INVALIDATION_CHANNEL,
    LOCK_INFO_KEY,
    MAX_BATCH_LIMIT,
    MAX_RETRY_SECONDS,
    CacheOutboxPublisher,
    OutboxDeliveryError,
    due_outbox_select,
    positive_version,
    promoted_binding_select,
    require_batch_limit,
    version_bump_message,
)


def _load_characterization():
    path = Path(__file__).with_name("test_evaluation_bounded_apply.py")
    name = "bounded_apply_sqlite_characterization"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_CHARACTER = _load_characterization()
db = _CHARACTER.db

BACKEND = Path(__file__).resolve().parents[1]
START = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)
FORBIDDEN = ("Outbox Sentinel", "Person 0", "manager_notes", "record_payload", "Ada")


class _Boom:
    """Any use, including bool(), is a test failure."""

    def __call__(self, *args, **kwargs):
        raise AssertionError("call")

    def __getattr__(self, name):
        raise AssertionError(name)

    def __bool__(self):
        raise AssertionError("bool")


class _Unset:
    pass


_UNSET = _Unset()


class _Client:
    def __init__(self, publish_result=0):
        self.calls = []
        self.version = 0
        self.publish_result = publish_result
        self.incr_error = None
        self.publish_error = None
        self.incr_result = _UNSET
        self.bool_calls = 0

    def __bool__(self):
        self.bool_calls += 1
        raise AssertionError("client truthiness")

    def incr(self, key):
        self.calls.append(("incr", key))
        if self.incr_error is not None:
            error = self.incr_error
            self.incr_error = None
            raise error
        if self.incr_result is not _UNSET:
            result = self.incr_result
            self.incr_result = _UNSET
            return result
        self.version += 1
        return self.version

    def publish(self, channel, message):
        self.calls.append(("publish", channel, message))
        if self.publish_error is not None:
            error = self.publish_error
            self.publish_error = None
            raise error
        return self.publish_result

    def delete(self, *args, **kwargs):
        raise AssertionError("delete")


class _Log(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


@contextmanager
def _sql(session):
    statements = []

    def before(conn, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))

    bind = session.get_bind()
    event.listen(bind, "before_cursor_execute", before)
    try:
        yield statements
    finally:
        event.remove(bind, "before_cursor_execute", before)


@contextmanager
def _logs():
    handler = _Log()
    publisher_module.logger.addHandler(handler)
    publisher_module.logger.setLevel(logging.WARNING)
    try:
        yield handler.messages
    finally:
        publisher_module.logger.removeHandler(handler)


def _clock(cell):
    return lambda: cell["now"]


def _aware(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _promote_coding(db):
    world, scope = _CHARACTER._bulk_coding(db, 1)
    captured = world.service.capture(world.actor, scope["id"], 2026, 7)
    _CHARACTER._stage_all(world.service, world.actor, captured["job_id"], 1)
    promoted = world.service.promote(world.actor, captured["job_id"])
    return world, promoted


def _team(db, world, name):
    return db.query(Team).filter(Team.id == world.team_ids[name]).one()


def _protect(db, world, name="Coding"):
    world.admin = db.query(User).filter(User.id == world.admin_id).one()
    return world.protect(_team(db, world, name))


def _promote_two(db):
    world = _CHARACTER._World(db, ("Coding", "Submission"))
    promoted = []
    for name in ("Coding", "Submission"):
        scope = world.scope(name)
        draft = world.ratio_draft(scope["id"], 7, 50)
        key = draft["lines"][0]["kpi_key"]
        team = _team(db, world, name)
        upload = world.upload_for(team, "July")
        employee = world.employee(team, f"{name[:1]}-1", "Outbox Sentinel")
        record = world.record(employee, "July", "70.00", "D", upload=upload)
        world.kpi(record, key, "60", "40")
        db.commit()
        _CHARACTER._approve(world.workflow, world.actor, draft["id"])
        captured = world.service.capture(world.actor, scope["id"], 2026, 7)
        _CHARACTER._stage_all(world.service, world.actor, captured["job_id"], 1)
        promoted.append(world.service.promote(world.actor, captured["job_id"]))
    return world, promoted


def _rows(db):
    db.expire_all()
    return (
        db.query(CacheInvalidationOutbox)
        .order_by(CacheInvalidationOutbox.created_at.asc(), CacheInvalidationOutbox.id.asc())
        .all()
    )


def _image(row) -> tuple:
    return (
        str(row.id),
        str(row.job_id),
        str(row.revision_id),
        row.namespace,
        row.dedup_key,
        _aware(row.created_at),
        int(row.delivery_attempts),
        _aware(row.next_retry_at),
        _aware(row.published_at),
        row.last_error,
    )


def _images(db) -> tuple:
    return tuple(_image(row) for row in _rows(db))


def _due_ids(db, now):
    return [
        row.id
        for row in db.query(CacheInvalidationOutbox)
        .filter(
            CacheInvalidationOutbox.namespace == "data",
            CacheInvalidationOutbox.published_at.is_(None),
        )
        .order_by(CacheInvalidationOutbox.next_retry_at.asc(), CacheInvalidationOutbox.id.asc())
        .all()
        if row.next_retry_at is None or _aware(row.next_retry_at) <= now
    ]


def _assert_clean(text: str) -> None:
    for needle in FORBIDDEN:
        assert needle not in text, needle


def _summary_ok(summary, *, published, failed, considered):
    assert set(summary) == {"enabled", "considered", "published", "failed"}
    assert summary == {
        "enabled": True,
        "considered": considered,
        "published": published,
        "failed": failed,
    }
    _assert_clean(repr(summary))


def _kind(statement: str) -> str:
    compact = " ".join(statement.lower().split())
    if "cache_invalidation_outbox" in compact and compact.startswith("select"):
        return "outbox-select"
    if "cache_invalidation_outbox" in compact and compact.startswith("update"):
        return "outbox-update"
    if "evaluation_apply_controls" in compact and compact.startswith("select"):
        return "binding-select"
    return compact


def _containers():
    found = {}
    for key, value in vars(publisher_module).items():
        if key.startswith("__"):
            continue
        if isinstance(value, (dict, list, set)):
            found[key] = (type(value), repr(value))
    return found


def test_disabled_call_does_not_query_or_touch_the_client():
    publisher = CacheOutboxPublisher(_Boom(), _Boom(), clock=_Boom())
    for value in (False, None, 0, 1, "true"):
        summary = publisher.deliver_due() if value is False else publisher.deliver_due(enabled=value)
        assert summary == {"enabled": False, "considered": 0, "published": 0, "failed": 0}
    signature = inspect.signature(CacheOutboxPublisher.deliver_due)
    assert signature.parameters["enabled"].default is False
    assert signature.parameters["limit"].default == DEFAULT_BATCH_LIMIT
    assert DEFAULT_BATCH_LIMIT <= MAX_BATCH_LIMIT

    source = (BACKEND / "services" / "evaluation" / "outbox_publisher.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = []
    attributes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
        elif isinstance(node, ast.Attribute):
            attributes.add(node.attr)
    for name in imported:
        assert name.split(".")[0] not in {
            "app",
            "worker",
            "redis",
            "socket",
            "settings",
        }
        assert "cache_invalidation_service" not in name
        assert "cache_service" not in name
        assert "redis_provider" not in name
    assert "delete" not in attributes
    assert "flushdb" not in attributes
    assert "flushall" not in attributes
    for relative in (
        "worker.py",
        "services/__init__.py",
        "services/evaluation/__init__.py",
        "app.py",
    ):
        text = (BACKEND / relative).read_text(encoding="utf-8")
        assert "outbox_publisher" not in text
        assert "CacheOutboxPublisher" not in text


def test_batch_limit_and_clock_reject_before_any_sql(db):
    publisher = CacheOutboxPublisher(_Boom(), _Boom(), clock=lambda: START)
    with _sql(db) as statements:
        for value in (True, False, 1.0, 1.5, "20", None, 0, -1, MAX_BATCH_LIMIT + 1, 10**9):
            with pytest.raises(OutboxDeliveryError) as caught:
                publisher.deliver_due(enabled=True, limit=value)
            assert caught.value.code == "invalid_batch_limit"
            assert str(caught.value) == "invalid_batch_limit"
    assert statements == []
    assert require_batch_limit(1) == 1
    assert require_batch_limit(MAX_BATCH_LIMIT) == MAX_BATCH_LIMIT

    naive = CacheOutboxPublisher(db, _Boom(), clock=lambda: datetime(2026, 10, 10, 8, 0))
    with _sql(db) as statements:
        with pytest.raises(OutboxDeliveryError) as caught:
            naive.deliver_due(enabled=True, limit=1)
        assert caught.value.code == "invalid_clock"
    assert statements == []

    client = _Client()
    empty = CacheOutboxPublisher(db, client, clock=lambda: START)
    with _sql(db) as statements:
        summary = empty.deliver_due(enabled=True, limit=MAX_BATCH_LIMIT)
    _summary_ok(summary, published=0, failed=0, considered=0)
    assert client.calls == []
    assert client.bool_calls == 0
    assert len(statements) == 1
    assert _kind(statements[0][0]) == "outbox-select"
    assert "LIMIT" in statements[0][0].upper()


def test_postgresql_lock_sql_is_outbox_skip_locked_only():
    now = START
    locked = due_outbox_select(now, 1, lock=True)
    rendered = str(locked.compile(dialect=postgresql.dialect())).lower()
    assert "for update" in rendered
    assert "skip locked" in rendered
    assert "cache_invalidation_outbox" in rendered
    assert "offset" not in rendered
    assert locked._offset_clause is None
    for forbidden in (
        "performance_records",
        "kpi_values",
        "employees",
        "evaluation_apply_stage_rows",
        "evaluation_apply_controls",
        "evaluation_scopes",
        "processing_jobs",
        "actor_snapshot",
        "teams",
        "users",
    ):
        assert forbidden not in rendered
    plain = due_outbox_select(now, DEFAULT_BATCH_LIMIT, lock=False)
    plain_sql = str(plain.compile(dialect=postgresql.dialect())).lower()
    assert "for update" not in plain_sql
    assert plain._offset_clause is None
    binding = promoted_binding_select([uuid.uuid4()])
    binding_sql = str(binding.compile(dialect=postgresql.dialect())).lower()
    assert "promoted_revision_id" in binding_sql
    assert "for update" not in binding_sql
    assert "actor_snapshot" not in binding_sql
    assert positive_version(True) is None
    assert positive_version(False) is None
    assert positive_version(0) is None
    assert positive_version(1) == 1


def test_success_with_zero_subscribers_is_immutable_without_authority(db):
    fallback = _fallback_data_version
    world, _promoted = _promote_coding(db)
    protected = _protect(db, world)
    admin = db.query(User).filter(User.id == world.admin_id).one()
    admin.role = "Performance Team"
    admin.is_active = False
    for team in db.query(Team).all():
        team.is_active = False
    db.commit()
    live = _CHARACTER._live(db)
    before = _images(db)
    assert before[0][6] == 0
    assert before[0][8] is None
    client = _Client(publish_result=0)
    cell = {"now": START}
    publisher = CacheOutboxPublisher(db, client, clock=_clock(cell))
    with _sql(db) as skipped:
        skipped_summary = publisher.deliver_due(limit=1)
    assert skipped == []
    assert skipped_summary["enabled"] is False
    assert client.calls == []
    assert _images(db) == before

    db.expunge_all()
    with _logs() as messages:
        summary = publisher.deliver_due(enabled=True, limit=1)
    _summary_ok(summary, published=1, failed=0, considered=1)
    assert messages == []
    assert client.bool_calls == 0
    assert client.calls == [
        ("incr", DATA_VERSION_KEY),
        (
            "publish",
            INVALIDATION_CHANNEL,
            '{"action": "version_bump", "type": "data", "version": 1}',
        ),
    ]
    assert client.calls[1][2] == version_bump_message(1)
    _assert_clean(client.calls[1][2])
    published = _images(db)
    assert published[0][6] == 1
    assert published[0][7] is None
    assert published[0][8] == START
    assert published[0][9] is None
    assert published[0][:6] == before[0][:6]
    restarted = CacheOutboxPublisher(db, client, clock=_clock(cell))
    again = restarted.deliver_due(enabled=True, limit=1)
    _summary_ok(again, published=0, failed=0, considered=0)
    assert _images(db) == published
    assert len(client.calls) == 2
    assert _CHARACTER._live(db) == live
    assert world.workflow.protected_texts() == protected
    assert db.query(CacheInvalidationOutbox).count() == 1
    assert db.query(PerformanceRecord).count() == 1
    assert _fallback_data_version == fallback
    control = db.query(EvaluationApplyControl).one()
    assert control.state == "promoted"
    assert control.requested_by_user_id == world.admin_id


def test_absent_client_backoff_is_bounded_and_a_new_instance_can_finish(db):
    fallback = _fallback_data_version
    _promote_coding(db)
    live = _CHARACTER._live(db)
    cell = {"now": START}
    publisher = CacheOutboxPublisher(db, None, clock=_clock(cell))
    delays = []
    for expected in (30, 60, 120, 240, 480, 900, 900):
        current = _rows(db)[0]
        due = START if current.next_retry_at is None else _aware(current.next_retry_at)
        cell["now"] = due
        summary = publisher.deliver_due(enabled=True, limit=1)
        _summary_ok(summary, published=0, failed=1, considered=1)
        fresh = _rows(db)[0]
        assert fresh.published_at is None
        assert fresh.last_error == DELIVERY_ERRORS["client_unavailable"]
        assert len(fresh.last_error) <= 240
        delays.append(int((_aware(fresh.next_retry_at) - due).total_seconds()))
        assert expected <= MAX_RETRY_SECONDS
    assert delays == [30, 60, 120, 240, 480, 900, 900]
    fresh = _rows(db)[0]
    assert fresh.delivery_attempts == 7
    cell["now"] = _aware(fresh.next_retry_at) - timedelta(seconds=1)
    skipped = publisher.deliver_due(enabled=True, limit=1)
    _summary_ok(skipped, published=0, failed=0, considered=0)
    assert _rows(db)[0].delivery_attempts == 7
    cell["now"] = _aware(fresh.next_retry_at)
    client = _Client(publish_result=0)
    finished = CacheOutboxPublisher(db, client, clock=_clock(cell)).deliver_due(enabled=True, limit=1)
    _summary_ok(finished, published=1, failed=0, considered=1)
    done = _rows(db)[0]
    assert done.delivery_attempts == 8
    assert done.published_at is not None
    assert done.last_error is None
    assert done.next_retry_at is None
    assert client.version == 1
    assert client.calls[1][2] == version_bump_message(1)
    held = _image(done)
    idle = CacheOutboxPublisher(db, client, clock=_clock(cell)).deliver_due(enabled=True, limit=1)
    _summary_ok(idle, published=0, failed=0, considered=0)
    assert _image(_rows(db)[0]) == held
    assert len(client.calls) == 2
    assert _CHARACTER._live(db) == live
    assert _fallback_data_version == fallback


def test_redis_failures_and_invalid_replies_do_not_acknowledge(db):
    fallback = _fallback_data_version
    containers = _containers()
    _promote_coding(db)
    live = _CHARACTER._live(db)
    before = _images(db)
    client = _Client(publish_result=0)
    cell = {"now": START}
    publisher = CacheOutboxPublisher(db, client, clock=_clock(cell))
    sentinel = "Outbox Sentinel score 100 Coding manager_notes Person 0"
    cases = [
        ("increment_failed", lambda: setattr(client, "incr_error", RuntimeError(sentinel)), False),
        ("increment_reply_invalid", lambda: setattr(client, "incr_result", True), False),
        ("increment_reply_invalid", lambda: setattr(client, "incr_result", False), False),
        ("increment_reply_invalid", lambda: setattr(client, "incr_result", 0), False),
        ("increment_reply_invalid", lambda: setattr(client, "incr_result", -2), False),
        ("increment_reply_invalid", lambda: setattr(client, "incr_result", 1.0), False),
        ("increment_reply_invalid", lambda: setattr(client, "incr_result", "1"), False),
        ("increment_reply_invalid", lambda: setattr(client, "incr_result", None), False),
        ("publish_failed", lambda: setattr(client, "publish_error", ConnectionError(sentinel)), True),
        ("publish_reply_invalid", lambda: setattr(client, "publish_result", True), True),
        ("publish_reply_invalid", lambda: setattr(client, "publish_result", False), True),
        ("publish_reply_invalid", lambda: setattr(client, "publish_result", -1), True),
        ("publish_reply_invalid", lambda: setattr(client, "publish_result", 0.0), True),
        ("publish_reply_invalid", lambda: setattr(client, "publish_result", "0"), True),
    ]
    with _logs() as messages:
        for index, (code, setup, publish_expected) in enumerate(cases, start=1):
            current = _rows(db)[0]
            cell["now"] = START if current.next_retry_at is None else _aware(current.next_retry_at)
            calls_before = len(client.calls)
            setup()
            summary = publisher.deliver_due(enabled=True, limit=1)
            _summary_ok(summary, published=0, failed=1, considered=1)
            fresh = _rows(db)[0]
            assert fresh.published_at is None
            assert fresh.delivery_attempts == index
            assert fresh.last_error == DELIVERY_ERRORS[code]
            assert sentinel not in fresh.last_error
            assert fresh.dedup_key == before[0][4]
            new_calls = client.calls[calls_before:]
            assert new_calls[0] == ("incr", DATA_VERSION_KEY)
            if publish_expected:
                assert new_calls[1][0] == "publish"
                assert new_calls[1][1] == INVALIDATION_CHANNEL
                _assert_clean(new_calls[1][2])
            else:
                assert all(call[0] != "publish" for call in new_calls)
            client.publish_result = 0
    assert messages
    for message in messages:
        _assert_clean(message)
        assert "version_bump" not in message
    cell["now"] = _aware(_rows(db)[0].next_retry_at)
    client.publish_result = 3
    restarted = CacheOutboxPublisher(db, client, clock=_clock(cell))
    summary = restarted.deliver_due(enabled=True, limit=1)
    _summary_ok(summary, published=1, failed=0, considered=1)
    done = _rows(db)[0]
    assert done.delivery_attempts == len(cases) + 1
    assert _aware(done.published_at) == cell["now"]
    assert done.last_error is None
    assert done.next_retry_at is None
    assert client.calls[-1][2] == version_bump_message(client.version)
    assert _CHARACTER._live(db) == live
    assert _fallback_data_version == fallback
    assert _containers() == containers


def test_crash_after_external_success_does_not_persist_or_suppress_retry(db):
    fallback = _fallback_data_version
    containers = _containers()
    _promote_coding(db)
    live = _CHARACTER._live(db)
    original = _images(db)
    client = _Client(publish_result=0)
    cell = {"now": START}
    db.info[FAULT_INFO_KEY] = FAULT_AFTER_PUBLISH_BEFORE_ACK
    with pytest.raises(OutboxDeliveryError) as first:
        CacheOutboxPublisher(db, client, clock=_clock(cell)).deliver_due(enabled=True, limit=1)
    assert first.value.code == "acknowledgment_failed"
    assert str(first.value) == "acknowledgment_failed"
    assert first.value.__cause__ is None
    assert _images(db) == original
    assert client.version == 1
    assert client.calls[-1][2] == version_bump_message(1)

    db.info[FAULT_INFO_KEY] = FAULT_BEFORE_ACK_COMMIT
    with pytest.raises(OutboxDeliveryError) as second:
        CacheOutboxPublisher(db, client, clock=_clock(cell)).deliver_due(enabled=True, limit=1)
    assert second.value.code == "acknowledgment_failed"
    assert _images(db) == original
    assert client.version == 2

    db.info.pop(FAULT_INFO_KEY, None)
    restarted = CacheOutboxPublisher(db, client, clock=_clock(cell))
    summary = restarted.deliver_due(enabled=True, limit=1)
    _summary_ok(summary, published=1, failed=0, considered=1)
    done = _rows(db)[0]
    assert done.delivery_attempts == 1
    assert _aware(done.published_at) == START
    assert done.last_error is None
    assert client.version == 3
    assert client.calls[-1] == (
        "publish",
        INVALIDATION_CHANNEL,
        version_bump_message(3),
    )
    held = _image(done)
    assert CacheOutboxPublisher(db, client, clock=_clock(cell)).deliver_due(enabled=True)["published"] == 0
    assert _image(_rows(db)[0]) == held
    assert client.version == 3
    assert _CHARACTER._live(db) == live
    assert _fallback_data_version == fallback
    assert _containers() == containers


def test_batch_retains_one_row_and_a_fixed_query_budget(db):
    fallback = _fallback_data_version
    world, _promoted = _promote_two(db)
    protected = _protect(db, world)
    live = _CHARACTER._live(db)
    now = START
    ordered = _due_ids(db, now)
    assert len(ordered) == 2
    db.expunge_all()
    seen = {}

    def after_lock(ids):
        objects = list(db.identity_map.values())
        seen["ids"] = ids
        seen["names"] = sorted(type(obj).__name__ for obj in objects)

    db.info[LOCK_INFO_KEY] = after_lock
    client = _Client(publish_result=0)
    publisher = CacheOutboxPublisher(db, client, clock=lambda: now)
    with _sql(db) as statements:
        summary = publisher.deliver_due(enabled=True, limit=1)
    _summary_ok(summary, published=1, failed=0, considered=1)
    assert seen["ids"] == (ordered[0],)
    assert seen["names"] == ["CacheInvalidationOutbox"]
    assert [_kind(statement) for statement, _parameters in statements] == [
        "outbox-select",
        "binding-select",
        "outbox-update",
    ]
    rendered = "\n".join(statement for statement, _parameters in statements).lower()
    for forbidden in (
        "performance_records",
        "kpi_values",
        "employees",
        "evaluation_apply_stage_rows",
        "actor_snapshot",
        "record_payload",
        "before_row",
        "processing_jobs",
        "evaluation_scopes",
        " from users",
        " from teams",
    ):
        assert forbidden not in rendered
    assert "for update" not in rendered
    select_sql, select_params = statements[0]
    assert "offset 1" not in select_sql.lower()
    # SQLite renders a bound OFFSET even when the statement has no offset clause.
    if isinstance(select_params, dict):
        integers = [value for value in select_params.values() if type(value) is int]
    else:
        integers = [value for value in select_params if type(value) is int]
    assert integers == [1, 0]
    assert all(name not in {type(obj).__name__ for obj in db.identity_map.values()} for name in (
        "PerformanceRecord",
        "KPIValue",
        "Employee",
        "EvaluationApplyStageRow",
        "EvaluationApplyControl",
    ))
    rows = _rows(db)
    by_id = {row.id: row for row in rows}
    assert by_id[ordered[0]].published_at is not None
    assert by_id[ordered[0]].delivery_attempts == 1
    assert by_id[ordered[1]].published_at is None
    assert by_id[ordered[1]].delivery_attempts == 0
    assert by_id[ordered[1]].last_error is None
    assert by_id[ordered[1]].next_retry_at is None
    first_image = _image(by_id[ordered[0]])
    db.info.pop(LOCK_INFO_KEY, None)
    client.publish_result = 4
    second = CacheOutboxPublisher(db, client, clock=lambda: now).deliver_due(enabled=True, limit=1)
    _summary_ok(second, published=1, failed=0, considered=1)
    rows = _rows(db)
    by_id = {row.id: row for row in rows}
    assert _image(by_id[ordered[0]]) == first_image
    assert by_id[ordered[1]].delivery_attempts == 1
    assert by_id[ordered[1]].published_at is not None
    assert client.calls[-1][2] == version_bump_message(2)
    assert json.loads(client.calls[-1][2]) == {
        "action": "version_bump",
        "type": "data",
        "version": 2,
    }
    assert _CHARACTER._live(db) == live
    assert world.workflow.protected_texts() == protected
    assert db.query(CacheInvalidationOutbox).count() == 2
    assert _fallback_data_version == fallback


@pytest.mark.parametrize("point", ["scalars", "flush", "commit"])
def test_database_failure_rolls_back_before_retry_without_raw_details(db, monkeypatch, point):
    _promote_coding(db)
    original_image = _images(db)
    live = _CHARACTER._live(db)
    client = _Client()
    original = getattr(db, point)
    original_rollback = db.rollback
    rollbacks = []

    def fail(*args, **kwargs):
        raise RuntimeError("Outbox Sentinel Person 0 private SQL fault")

    def rollback():
        rollbacks.append(True)
        return original_rollback()

    monkeypatch.setattr(db, point, fail)
    monkeypatch.setattr(db, "rollback", rollback)
    with pytest.raises(OutboxDeliveryError) as caught:
        CacheOutboxPublisher(db, client, clock=lambda: START).deliver_due(enabled=True)
    assert str(caught.value) == "acknowledgment_failed"
    assert caught.value.__cause__ is None
    assert rollbacks == [True]
    monkeypatch.setattr(db, point, original)
    assert _images(db) == original_image
    external_successes = 0 if point == "scalars" else 1
    assert client.version == external_successes
    result = CacheOutboxPublisher(db, client, clock=lambda: START).deliver_due(enabled=True)
    _summary_ok(result, published=1, failed=0, considered=1)
    assert client.version == external_successes + 1
    assert _rows(db)[0].delivery_attempts == 1
    assert _CHARACTER._live(db) == live


def test_second_row_failure_rolls_back_all_delivery_acknowledgments(db, monkeypatch):
    _promote_two(db)
    original_image = _images(db)
    live = _CHARACTER._live(db)
    client = _Client()
    publisher = CacheOutboxPublisher(db, client, clock=lambda: START)
    mark_success = publisher._mark_success
    successes = []

    def mark_then_fail_second(row, now):
        mark_success(row, now)
        successes.append(row.id)
        if len(successes) == 2:
            raise RuntimeError("Outbox Sentinel later-batch fault")

    monkeypatch.setattr(publisher, "_mark_success", mark_then_fail_second)
    with pytest.raises(OutboxDeliveryError) as caught:
        publisher.deliver_due(enabled=True, limit=2)
    assert str(caught.value) == "acknowledgment_failed"
    assert client.version == 2
    assert _images(db) == original_image
    result = CacheOutboxPublisher(db, client, clock=lambda: START).deliver_due(enabled=True, limit=2)
    _summary_ok(result, published=2, failed=0, considered=2)
    assert client.version == 4
    assert all(row.delivery_attempts == 1 for row in _rows(db))
    assert _CHARACTER._live(db) == live
