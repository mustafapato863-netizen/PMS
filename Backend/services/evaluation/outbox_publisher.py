"""Dormant at-least-once delivery for cache invalidation outbox rows.

Nothing calls this service. There is no setting, worker branch, or route.
``deliver_due`` does no work unless ``enabled is True``. A truthy flag is
not enough, and the Redis client is never tested with ``bool()`` because
``LazyRedisClient`` connects on truthiness and can report a process-local
version that is not a publish.

One call locks at most ``MAX_BATCH_LIMIT`` due ``data`` rows, ordered by
``next_retry_at`` then ``id``, with no offset. On PostgreSQL the lock is
``FOR UPDATE SKIP LOCKED`` of ``cache_invalidation_outbox`` only. Job,
scope, control, team, and performance rows are not locked. The promoted
revision is compared as a scalar. The stored actor snapshot, the
requester's current role, and the team's active flag are not read.

Delivery is direct ``INCR pms:version:data`` and ``PUBLISH
cache_invalidation``. ``published_at`` is committed only after both
commands return a valid reply and the database commit returns. A crash
after Redis and before that commit leaves the row unpublished. The next
attempt may increment again. That is at least once. This module keeps no
delivered-id set and does not call the cache fallback counter.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from models.models import CacheInvalidationOutbox, EvaluationApplyControl
from services.evaluation.apply_job_schema import NAMESPACE_DATA, OUTBOX_ERROR_LIMIT


logger = logging.getLogger(__name__)

DEFAULT_BATCH_LIMIT = 20
MAX_BATCH_LIMIT = 25
BASE_RETRY_SECONDS = 30
MAX_RETRY_SECONDS = 900
DATA_VERSION_KEY = "pms:version:data"
INVALIDATION_CHANNEL = "cache_invalidation"
FAULT_INFO_KEY = "outbox_publisher_fault"
LOCK_INFO_KEY = "outbox_publisher_after_lock"
FAULT_AFTER_PUBLISH_BEFORE_ACK = "after_publish_before_ack"
FAULT_BEFORE_ACK_COMMIT = "before_ack_commit"

DELIVERY_ERRORS = {
    "client_unavailable": "cache delivery client unavailable",
    "increment_failed": "cache delivery increment failed",
    "increment_reply_invalid": "cache delivery increment reply invalid",
    "publish_failed": "cache delivery publish failed",
    "publish_reply_invalid": "cache delivery publish reply invalid",
    "binding_missing": "cache delivery revision binding missing",
}

if any(not text or len(text) > OUTBOX_ERROR_LIMIT for text in DELIVERY_ERRORS.values()):
    raise RuntimeError("cache delivery errors must be short generic text")


class OutboxDeliveryError(Exception):
    """Generic delivery failure. The message is a stable code, not row data."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def require_batch_limit(value) -> int:
    """Accept only a real integer from 1 through the documented maximum.

    ``bool`` is rejected because it is a subclass of ``int``. Floats,
    strings, and ``None`` are rejected so a caller cannot ask for an
    unbounded scan.
    """

    if type(value) is not int or value < 1 or value > MAX_BATCH_LIMIT:
        raise OutboxDeliveryError("invalid_batch_limit")
    return value


def positive_version(value) -> int | None:
    """Redis INCR must return a positive integer. Booleans are not integers here."""

    if type(value) is not int or value < 1:
        return None
    return value


def accepted_subscriber_count(value) -> bool:
    """A PUBLISH reply of 0 means Redis accepted the command."""

    return type(value) is int and value >= 0


def version_bump_message(version: int) -> str:
    """The existing generic data-version message. No scope or score fields."""

    return json.dumps({"action": "version_bump", "type": "data", "version": version})


def retry_delay(attempts: int) -> timedelta:
    """Bounded exponential delay. ``attempts`` is the count after this failure."""

    exponent = min(max(int(attempts) - 1, 0), 5)
    seconds = min(BASE_RETRY_SECONDS * (2 ** exponent), MAX_RETRY_SECONDS)
    return timedelta(seconds=seconds)


def due_outbox_select(now: datetime, limit: int, *, lock: bool):
    """One keyset page of due unpublished data rows.

    ``lock`` adds PostgreSQL ``FOR UPDATE SKIP LOCKED`` for this table only.
    SQLite has no row lock, so callers pass ``lock=False`` there. The
    statement has a limit and no offset.
    """

    statement = (
        select(CacheInvalidationOutbox)
        .where(
            CacheInvalidationOutbox.namespace == NAMESPACE_DATA,
            CacheInvalidationOutbox.published_at.is_(None),
            or_(
                CacheInvalidationOutbox.next_retry_at.is_(None),
                CacheInvalidationOutbox.next_retry_at <= now,
            ),
        )
        .order_by(
            CacheInvalidationOutbox.next_retry_at.asc(),
            CacheInvalidationOutbox.id.asc(),
        )
        .limit(limit)
    )
    if lock:
        statement = statement.with_for_update(
            skip_locked=True,
            of=CacheInvalidationOutbox,
        )
    return statement


def promoted_binding_select(job_ids):
    """Scalar promoted-revision check. It does not lock the control row."""

    return select(
        EvaluationApplyControl.job_id,
        EvaluationApplyControl.promoted_revision_id,
    ).where(
        EvaluationApplyControl.job_id.in_(tuple(job_ids)),
        EvaluationApplyControl.state == "promoted",
    )


def _summary(enabled: bool, considered: int, published: int, failed: int) -> dict:
    return {
        "enabled": enabled,
        "considered": considered,
        "published": published,
        "failed": failed,
    }


def _same_id(left, right) -> bool:
    if left is None or right is None:
        return False
    try:
        return uuid.UUID(str(left)) == uuid.UUID(str(right))
    except (TypeError, ValueError, AttributeError):
        return False


class CacheOutboxPublisher:
    """Deliver one bounded page of due outbox rows, then commit that page."""

    def __init__(self, db, client=None, clock=None) -> None:
        self.db = db
        self.client = client
        self.clock = clock

    def deliver_due(self, *, enabled: bool = False, limit: int = DEFAULT_BATCH_LIMIT) -> dict:
        """Publish due rows only when ``enabled is True``.

        The call ends its own transaction. Callers commit their own writes
        first. A Redis failure is committed as one more attempt and a future
        ``next_retry_at``. A database failure after Redis rolls back and
        raises ``OutboxDeliveryError``; the summary is not returned.
        """

        if enabled is not True:
            return _summary(False, 0, 0, 0)
        checked = require_batch_limit(limit)
        now = self._now()
        try:
            rows = self._lock_due(now, checked)
            if not rows:
                self.db.rollback()
                return _summary(True, 0, 0, 0)
            self._notify_locked(rows)
            bindings = self._bindings([row.job_id for row in rows])
            published = 0
            failed = 0
            for row in rows:
                if self._deliver_row(row, now, bindings):
                    published += 1
                else:
                    failed += 1
            self.db.flush()
            self._fault(FAULT_BEFORE_ACK_COMMIT)
            self.db.commit()
        except OutboxDeliveryError:
            self.db.rollback()
            raise
        except AssertionError:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise OutboxDeliveryError("acknowledgment_failed") from None
        for row in rows:
            self.db.expunge(row)
        return _summary(True, len(rows), published, failed)

    def _now(self) -> datetime:
        clock = self.clock
        current = datetime.now(timezone.utc) if clock is None else clock()
        if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
            raise OutboxDeliveryError("invalid_clock")
        return current

    def _lock_due(self, now: datetime, limit: int):
        dialect = self.db.get_bind().dialect.name
        statement = due_outbox_select(now, limit, lock=dialect == "postgresql")
        statement = statement.execution_options(populate_existing=True)
        return list(self.db.scalars(statement).all())

    def _notify_locked(self, rows) -> None:
        callback = self.db.info.get(LOCK_INFO_KEY)
        if callback is None:
            return
        callback(tuple(row.id for row in rows))

    def _bindings(self, job_ids) -> dict:
        if not job_ids:
            return {}
        found = {}
        for job_id, revision_id in self.db.execute(promoted_binding_select(job_ids)):
            found[str(job_id)] = revision_id
        return found

    def _deliver_row(self, row, now: datetime, bindings: dict) -> bool:
        if not _same_id(bindings.get(str(row.job_id)), row.revision_id):
            self._mark_failure(row, now, "binding_missing")
            return False
        client = self.client
        if client is None:
            self._mark_failure(row, now, "client_unavailable")
            return False
        try:
            raw_version = client.incr(DATA_VERSION_KEY)
        except Exception:
            self._mark_failure(row, now, "increment_failed")
            return False
        version = positive_version(raw_version)
        if version is None:
            self._mark_failure(row, now, "increment_reply_invalid")
            return False
        message = version_bump_message(version)
        try:
            raw_count = client.publish(INVALIDATION_CHANNEL, message)
        except Exception:
            self._mark_failure(row, now, "publish_failed")
            return False
        if not accepted_subscriber_count(raw_count):
            self._mark_failure(row, now, "publish_reply_invalid")
            return False
        self._fault(FAULT_AFTER_PUBLISH_BEFORE_ACK)
        self._mark_success(row, now)
        return True

    def _mark_success(self, row, now: datetime) -> None:
        row.delivery_attempts = int(row.delivery_attempts) + 1
        row.published_at = now
        row.next_retry_at = None
        row.last_error = None

    def _mark_failure(self, row, now: datetime, code: str) -> None:
        attempts = int(row.delivery_attempts) + 1
        row.delivery_attempts = attempts
        row.last_error = DELIVERY_ERRORS[code]
        row.next_retry_at = now + retry_delay(attempts)
        logger.warning("cache outbox delivery retained: %s", code)

    def _fault(self, point: str) -> None:
        if self.db.info.get(FAULT_INFO_KEY) == point:
            raise OutboxDeliveryError("acknowledgment_failed")
