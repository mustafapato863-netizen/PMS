"""Tests for ReadOnlySessionGuard database and savepoint safety."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import ProductSetting
from services.ai import read_only_guard as guard_module
from services.ai.read_only_guard import AI_READ_ONLY_WRITE_ERROR, ReadOnlySessionGuard


def _make_sqlite_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_read_only_guard_blocks_writes_and_reverts_dirty_sqlite_state():
    db = _make_sqlite_session()
    setting = ProductSetting(key="sample_setting", enabled=False)
    db.add(setting)
    db.commit()

    with pytest.raises(RuntimeError, match=AI_READ_ONLY_WRITE_ERROR):
        with ReadOnlySessionGuard(db):
            setting.enabled = True
            db.flush()

    assert setting.enabled is False


def test_read_only_guard_uses_savepoint_for_postgresql_set_transaction_read_only(monkeypatch):
    """On PostgreSQL, a failing SET TRANSACTION READ ONLY rolls back only a nested savepoint."""
    nested_entered = []
    nested_exited = []
    executed_sql = []

    monkeypatch.setattr(guard_module.event, "listen", lambda *_a, **_k: None)
    monkeypatch.setattr(guard_module.event, "remove", lambda *_a, **_k: None)

    class _FakeDialect:
        name = "postgresql"

    class _FakeConn:
        dialect = _FakeDialect()
        info: dict = {}

        @contextmanager
        def begin_nested(self):
            nested_entered.append(True)
            try:
                yield
            except Exception as exc:
                nested_exited.append(type(exc).__name__)
                raise
            else:
                nested_exited.append("clean")

        def execute(self, stmt, *_args, **_kwargs):
            sql_text = str(stmt)
            executed_sql.append(sql_text)
            if "SET TRANSACTION READ ONLY" in sql_text:
                raise SQLAlchemyError("SET TRANSACTION READ ONLY must be called before any query")
            return MagicMock()

    fake_conn = _FakeConn()

    class _FakeSession:
        new = set()
        dirty = set()
        deleted = set()
        identity_map = {}

        @contextmanager
        def _no_autoflush(self):
            yield

        no_autoflush = property(lambda self: self._no_autoflush())

        def connection(self):
            return fake_conn

        def flush(self):
            return None

        def commit(self):
            return None

    session = _FakeSession()
    # Should NOT raise and should use conn.begin_nested() around SET TRANSACTION READ ONLY
    with ReadOnlySessionGuard(session) as guard:
        assert guard._read_only_transaction_applied is False

    assert nested_entered == [True]
    assert nested_exited == ["SQLAlchemyError"]
    assert any("SET TRANSACTION READ ONLY" in sql for sql in executed_sql)
