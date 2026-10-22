import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import ClassVar

from config.database import SessionLocal
from models.models import User
from repositories.user_repository import UserRepository


logger = logging.getLogger(__name__)

PRESENCE_ONLINE_WINDOW = timedelta(minutes=2)
PRESENCE_HEARTBEAT_WRITE_INTERVAL = timedelta(seconds=60)


class UserPresenceService:
    """Persist durable presence metadata outside the Socket.IO event layer."""

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def is_online(cls, last_seen_at: datetime | None, now: datetime | None = None) -> bool:
        """Treat recent server-recorded activity as an online presence lease."""
        if last_seen_at is None:
            return False
        current_time = cls._as_utc(now or datetime.now(timezone.utc))
        last_seen = cls._as_utc(last_seen_at)
        return last_seen >= current_time - PRESENCE_ONLINE_WINDOW

    # Per-process memo of the last persisted heartbeat per user. A heartbeat
    # inside the write interval is answered from here without touching the
    # database at all (no pool checkout), which removes ~1 DB round trip per
    # open tab every 30s.
    _recent_writes: ClassVar[dict[str, datetime]] = {}
    _recent_lock = threading.Lock()
    _RECENT_MAX = 10_000

    @classmethod
    def _remember(cls, user_id: str, written_at: datetime) -> None:
        with cls._recent_lock:
            if len(cls._recent_writes) >= cls._RECENT_MAX:
                cutoff = written_at - PRESENCE_HEARTBEAT_WRITE_INTERVAL
                for key in [k for k, v in cls._recent_writes.items() if v < cutoff]:
                    cls._recent_writes.pop(key, None)
                if len(cls._recent_writes) >= cls._RECENT_MAX:
                    cls._recent_writes.clear()
            cls._recent_writes[user_id] = written_at

    @classmethod
    def _recent(cls, user_id: str) -> datetime | None:
        with cls._recent_lock:
            return cls._recent_writes.get(user_id)

    @classmethod
    def forget(cls, user_id: str | None = None) -> None:
        with cls._recent_lock:
            if user_id is None:
                cls._recent_writes.clear()
            else:
                cls._recent_writes.pop(str(user_id), None)

    @classmethod
    def record_heartbeat(
        cls,
        db,
        user_id: str,
        seen_at: datetime | None = None,
    ) -> datetime | None:
        """Refresh an authenticated user's presence without writing on every ping.

        One short DB unit: a light column read and, at most once per write
        interval, a single UPDATE. Every path ends the transaction (commit or
        rollback), so the pooled connection goes back to the pool before the
        response is sent instead of sitting "idle in transaction" until the
        request's dependency teardown.
        """
        key = str(user_id)
        timestamp = cls._as_utc(seen_at or datetime.now(timezone.utc))
        cached = cls._recent(key)
        if cached is not None and timedelta(0) <= timestamp - cached < PRESENCE_HEARTBEAT_WRITE_INTERVAL:
            return cached
        try:
            try:
                parsed_id = uuid.UUID(key)
            except ValueError:
                return None
            row = (
                db.query(User.is_active, User.last_seen_at)
                .filter(User.id == parsed_id, User.is_active.is_(True))
                .first()
            )
            if row is None:
                db.rollback()
                cls.forget(key)
                return None
            last_seen = cls._as_utc(row.last_seen_at) if row.last_seen_at else None
            if last_seen and timestamp - last_seen < PRESENCE_HEARTBEAT_WRITE_INTERVAL:
                db.rollback()  # end the read transaction; releases the connection
                cls._remember(key, last_seen)
                return last_seen

            db.query(User).filter(User.id == parsed_id).update(
                {User.last_seen_at: timestamp}, synchronize_session=False
            )
            db.commit()
            cls._remember(key, timestamp)
            return timestamp
        except Exception:
            db.rollback()
            logger.exception("Failed to record presence heartbeat for user %s", user_id)
            raise

    @staticmethod
    def record_last_seen(user_id: str, seen_at: datetime | None = None) -> datetime | None:
        timestamp = seen_at or datetime.now(timezone.utc)
        db = SessionLocal()
        try:
            repository = UserRepository(db, User)
            if not repository.set_last_seen(user_id, timestamp):
                db.rollback()
                logger.warning("Skipped last-seen update for unknown user %s", user_id)
                return None
            db.commit()
            return timestamp
        except Exception:
            db.rollback()
            logger.exception("Failed to update last-seen time for user %s", user_id)
            return None
        finally:
            db.close()
