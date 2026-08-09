import logging
from datetime import datetime, timezone

from config.database import SessionLocal
from models.models import User
from repositories.user_repository import UserRepository


logger = logging.getLogger(__name__)


class UserPresenceService:
    """Persist durable presence metadata outside the Socket.IO event layer."""

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
