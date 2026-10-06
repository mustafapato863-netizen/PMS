import logging
from datetime import datetime, timedelta, timezone

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

    @classmethod
    def record_heartbeat(
        cls,
        db,
        user_id: str,
        seen_at: datetime | None = None,
    ) -> datetime | None:
        """Refresh an authenticated user's presence without writing on every ping."""
        timestamp = cls._as_utc(seen_at or datetime.now(timezone.utc))
        try:
            user = UserRepository(db, User).get_by_id(user_id)
            if not user or not user.is_active:
                return None

            last_seen = cls._as_utc(user.last_seen_at) if user.last_seen_at else None
            if last_seen and timestamp - last_seen < PRESENCE_HEARTBEAT_WRITE_INTERVAL:
                return last_seen

            user.last_seen_at = timestamp
            db.commit()
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
