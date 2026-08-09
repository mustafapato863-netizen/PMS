from datetime import datetime, timezone
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Base, User
from services.user_presence_service import UserPresenceService


def _session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[User.__table__])
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_record_last_seen_persists_exact_timestamp(monkeypatch):
    session_factory = _session_factory()
    user_id = uuid.uuid4()
    db = session_factory()
    db.add(
        User(
            id=user_id,
            username="presence_user",
            email="presence@test.com",
            full_name="Presence User",
            password_hash="not-used",
            role="Viewer",
        )
    )
    db.commit()
    db.close()
    monkeypatch.setattr(
        "services.user_presence_service.SessionLocal",
        session_factory,
    )
    seen_at = datetime(2026, 7, 28, 12, 30, tzinfo=timezone.utc)

    result = UserPresenceService.record_last_seen(str(user_id), seen_at)

    verify_db = session_factory()
    persisted = verify_db.get(User, user_id)
    assert result == seen_at
    assert persisted is not None
    assert persisted.last_seen_at.replace(tzinfo=timezone.utc) == seen_at
    verify_db.close()


def test_record_last_seen_ignores_unknown_user(monkeypatch):
    session_factory = _session_factory()
    monkeypatch.setattr(
        "services.user_presence_service.SessionLocal",
        session_factory,
    )

    result = UserPresenceService.record_last_seen(
        str(uuid.uuid4()),
        datetime(2026, 7, 28, tzinfo=timezone.utc),
    )

    verify_db = session_factory()
    assert result is None
    assert verify_db.query(User).count() == 0
    verify_db.close()


def test_record_last_seen_rolls_back_when_commit_fails(monkeypatch):
    class FailingSession:
        rolled_back = False
        closed = False

        def commit(self):
            raise RuntimeError("database unavailable")

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    session = FailingSession()
    monkeypatch.setattr(
        "services.user_presence_service.SessionLocal",
        lambda: session,
    )
    monkeypatch.setattr(
        "services.user_presence_service.UserRepository.set_last_seen",
        lambda self, user_id, seen_at: True,
    )

    result = UserPresenceService.record_last_seen(
        str(uuid.uuid4()),
        datetime(2026, 7, 28, tzinfo=timezone.utc),
    )

    assert result is None
    assert session.rolled_back is True
    assert session.closed is True
