"""Read-only session guard for AI tool reads (Phase 3, issue #96).

Every ``DeterministicToolRegistry`` entrypoint runs inside this guard. AI
read tools must never mutate database rows, approve actions, or coerce
``None`` to ``0``; the guard makes the first of those a hard runtime error
instead of a convention:

- ``session.flush()`` (and therefore ``session.commit()``, which flushes
  first, and SQLAlchemy autoflush before a query) raises
  ``RuntimeError("AI read tools cannot write to the database")`` while the
  guard is active **whenever the session actually carries pending writes**.
  A flush with nothing pending stays a harmless no-op, exactly like a
  real flush: SQLAlchemy autoflushes before every query, so blocking
  empty flushes would break every read the guard is meant to protect.
- A session that already carries pending ORM writes (``session.new`` /
  ``session.dirty``) at entry, or acquires any by exit, is rolled back and
  raises the same ``RuntimeError`` instead of letting the writes land.
- On PostgreSQL the guard additionally issues ``SET TRANSACTION READ ONLY``
  so the database itself rejects writes for the transaction; the statement
  is best-effort (a transaction that already ran statements cannot be
  flipped, and the flush block remains the enforcement). On SQLite test
  engines there is no equivalent statement and the guard is a clean no-op
  at the SQL level while the flush/dirty enforcement still applies.

The guard tolerates sessions it cannot protect (``None``, or a test double
without a real SQLAlchemy session): it stays inactive instead of raising,
so registry unit tests built on mock contexts keep working. Nested guards
on the same session collapse into the outermost one.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

AI_READ_ONLY_WRITE_ERROR = "AI read tools cannot write to the database"

_ACTIVE_ATTR = "_ai_read_only_guard_active"


def _is_session(value: Any) -> bool:
    """True for a real SQLAlchemy session (or anything flush-shaped)."""
    return value is not None and callable(getattr(value, "flush", None))


def _pending_writes(session: Any) -> bool:
    try:
        return bool(
            getattr(session, "new", None)
            or getattr(session, "dirty", None)
            or getattr(session, "deleted", None)
        )
    except Exception:
        return False


class ReadOnlySessionGuard:
    """Context manager enforcing read-only use of one SQLAlchemy session."""

    def __init__(self, db: Any = None, *, enforce: bool = True) -> None:
        self._db = db
        self._enforce = enforce
        self._active = False
        self._nested = False
        self._original_flush: Any = None
        self._read_only_transaction_applied = False

    @property
    def read_only_transaction_applied(self) -> bool:
        """True when ``SET TRANSACTION READ ONLY`` was accepted (PostgreSQL)."""
        return self._read_only_transaction_applied

    @property
    def active(self) -> bool:
        """True while this guard is the outermost active guard on its session."""
        return self._active

    def __enter__(self) -> "ReadOnlySessionGuard":
        session = self._db
        if not self._enforce or not _is_session(session):
            return self
        if getattr(session, _ACTIVE_ATTR, False):
            self._nested = True
            return self
        if _pending_writes(session):
            raise RuntimeError(AI_READ_ONLY_WRITE_ERROR)
        self._original_flush = session.flush

        def _blocked_flush(*args: Any, **kwargs: Any) -> Any:
            # SQLAlchemy autoflushes before every query even when nothing
            # is pending, so an unconditional raise would break all reads.
            # Block only a flush that would actually persist a change.
            if getattr(session, "new", None) or getattr(session, "dirty", None) or getattr(session, "deleted", None):
                raise RuntimeError(AI_READ_ONLY_WRITE_ERROR)
            return None

        session.flush = _blocked_flush  # type: ignore[method-assign]
        setattr(session, _ACTIVE_ATTR, True)
        self._active = True
        self._apply_read_only_transaction(session)
        return self

    def _apply_read_only_transaction(self, session: Any) -> None:
        """Issue ``SET TRANSACTION READ ONLY`` on PostgreSQL; no-op elsewhere."""
        try:
            bind = session.get_bind() if hasattr(session, "get_bind") else getattr(session, "bind", None)
            dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
        except Exception:
            dialect_name = None
        if dialect_name != "postgresql":
            return
        try:
            session.execute(text("SET TRANSACTION READ ONLY"))
        except SQLAlchemyError:
            # The transaction already ran statements and cannot be flipped;
            # roll the failed statement back so the session stays usable.
            # The flush block above remains the hard enforcement.
            logger.warning(
                "read-only guard: SET TRANSACTION READ ONLY was rejected; "
                "continuing with flush/dirty enforcement only"
            )
            try:
                session.rollback()
            except Exception:
                pass
            return
        self._read_only_transaction_applied = True

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if not self._active:
            return False
        session = self._db
        try:
            if _pending_writes(session):
                try:
                    session.rollback()
                except Exception:
                    pass
                if exc_type is None:
                    raise RuntimeError(AI_READ_ONLY_WRITE_ERROR)
                return False
            if self._read_only_transaction_applied:
                try:
                    if callable(getattr(session, "in_transaction", None)) and session.in_transaction():
                        session.rollback()
                except Exception:
                    pass
            return False
        finally:
            try:
                if self._original_flush is not None:
                    session.flush = self._original_flush  # type: ignore[method-assign]
            except Exception:
                pass
            try:
                setattr(session, _ACTIVE_ATTR, False)
            except Exception:
                pass
            self._active = False


def read_only_session(db: Any = None, *, enforce: bool = True) -> ReadOnlySessionGuard:
    """Alias for :class:`ReadOnlySessionGuard` (``with read_only_session(db):``)."""
    return ReadOnlySessionGuard(db, enforce=enforce)


def is_read_only_guarded(db: Any) -> bool:
    """True while a read-only guard is active on ``db``."""
    return bool(db is not None and getattr(db, _ACTIVE_ATTR, False))
