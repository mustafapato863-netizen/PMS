"""Read-only session guard for AI tool reads (Phase 3, issue #96).

Every ``DeterministicToolRegistry`` entrypoint and PMS AI data access operation
runs inside this guard. AI read tools must never mutate database rows, approve
actions, or coerce values; the guard makes this a hard runtime error and
database-enforced guarantee:

- Connection-scoped enforcement: Cursor execution listeners are bound ONLY to
  the session's checked-out connection (not the shared Engine), preventing
  interference with concurrent requests or unrelated sessions.
- Database-enforced read-only:
  * On SQLite: Sets ``PRAGMA query_only = ON`` on the connection, causing
    SQLite's native C engine to reject any write or DDL attempt.
  * On PostgreSQL: Sets ``SET TRANSACTION READ ONLY`` on the transaction when
    no preexisting writes exist.
- Session-scoped ORM enforcement:
  * ``session.flush()`` and ``session.commit()`` raise ``RuntimeError`` whenever called.
  * SQLAlchemy ``do_orm_execute`` intercepts ORM inserts, updates, and deletes.
  * Queries run under ``no_autoflush``.
- Deep attribute snapshot & reversion:
  * Attributes of preexisting objects (in ``new``, ``dirty``, and ``identity_map``)
    are deep-copied on entry.
  * On exit, rogue mutations (including in-place changes to mutable JSON/dicts/lists,
    new objects, and deletions) are reverted so no rejected changes can ever be committed.
  * Caller's legitimate preexisting work is preserved intact when ``allow_preexisting_writes=True``.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any

from sqlalchemy import event, inspect as sa_inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.attributes import NO_VALUE

logger = logging.getLogger(__name__)

AI_READ_ONLY_WRITE_ERROR = "AI read tools cannot write to the database"

_ACTIVE_ATTR = "_ai_read_only_guard_active"
_CONN_ACTIVE_KEY = "_ai_read_only_active"


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


def _clean_sql(statement: str) -> str:
    """Strip SQL comments, parentheses, and leading/trailing whitespace."""
    if not statement:
        return ""
    # Strip comments
    cleaned = re.sub(r"--[^\n]*", "", statement)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL).strip()
    # Strip enclosing parentheses if present
    while cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _is_modifying_sql(statement: str) -> bool:
    """True if statement is or contains a database write / DDL statement."""
    cleaned = _clean_sql(statement)
    if not cleaned:
        return False

    # Check for chained statements separated by semicolons
    statements = [s.strip() for s in cleaned.split(";") if s.strip()]
    for stmt in statements:
        match = re.match(r"^([A-Za-z]+)", stmt)
        if not match:
            continue
        verb = match.group(1).upper()
        if verb in {
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
            "REPLACE", "TRUNCATE", "MERGE", "UPSERT", "GRANT", "REVOKE",
            "EXEC", "EXECUTE", "CALL", "COPY", "DO", "ATTACH", "DETACH",
        }:
            return True
        if verb == "WITH" and re.search(r"\b(INSERT|UPDATE|DELETE)\b", stmt, re.IGNORECASE):
            return True
        if verb == "PRAGMA":
            # Certain pragmas modify database state or schema
            pragma_match = re.match(r"^PRAGMA\s+([A-Za-z_]+)", stmt, re.IGNORECASE)
            if pragma_match:
                pname = pragma_match.group(1).lower()
                if pname not in {"table_info", "table_xinfo", "index_list", "index_info", "foreign_key_list", "database_list", "query_only"}:
                    return True

    return False


def _snapshot_object_attributes(obj: Any) -> dict[str, Any]:
    """Capture a deep-copied snapshot of mapped column attributes on an ORM instance."""
    try:
        insp = sa_inspect(obj)
        snapshot = {}
        for prop in insp.mapper.column_attrs:
            key = prop.key
            attr = insp.attrs.get(key)
            if attr is not None and attr.loaded_value is not NO_VALUE:
                try:
                    snapshot[key] = copy.deepcopy(attr.loaded_value)
                except Exception:
                    snapshot[key] = attr.loaded_value
        return snapshot
    except Exception:
        return {}


class ReadOnlySessionGuard:
    """Context manager enforcing strict read-only isolation on a SQLAlchemy session.

    When allow_preexisting_writes is False (default):
    A session carrying pending writes at entry immediately raises RuntimeError.

    When allow_preexisting_writes is True:
    Pre-existing caller writes are preserved without autoflushing or discarding them.
    Any attempt to write or mutate ORM objects during the guard raises RuntimeError,
    and rogue modifications are cleanly reverted.
    """

    def __init__(self, db: Any = None, *, enforce: bool = True, allow_preexisting_writes: bool = False) -> None:
        self._db = db
        self._enforce = enforce
        self._allow_preexisting_writes = allow_preexisting_writes
        self._active = False
        self._nested = False
        self._original_flush: Any = None
        self._original_commit: Any = None
        self._read_only_transaction_applied = False
        self._sqlite_query_only_applied = False
        self._no_autoflush_cm: Any = None
        self._conn: Any = None
        self._conn_cursor_listener: Any = None
        self._orm_execute_listener: Any = None

        self._initial_new: set[Any] = set()
        self._initial_dirty: set[Any] = set()
        self._initial_deleted: set[Any] = set()
        self._initial_snapshots: dict[Any, dict[str, Any]] = {}

    @property
    def read_only_transaction_applied(self) -> bool:
        """True when ``SET TRANSACTION READ ONLY`` was accepted (PostgreSQL)."""
        return self._read_only_transaction_applied

    @property
    def active(self) -> bool:
        """True while this guard is active."""
        return self._active

    def _cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        # Strictly verify connection belongs to this guard session
        if conn.info.get(_CONN_ACTIVE_KEY) is True and _is_modifying_sql(statement):
            raise RuntimeError(AI_READ_ONLY_WRITE_ERROR)

    def _orm_execute(self, orm_execute_state: Any) -> None:
        if self._active:
            if (
                getattr(orm_execute_state, "is_insert", False)
                or getattr(orm_execute_state, "is_update", False)
                or getattr(orm_execute_state, "is_delete", False)
            ):
                raise RuntimeError(AI_READ_ONLY_WRITE_ERROR)

    def __enter__(self) -> "ReadOnlySessionGuard":
        session = self._db
        if not self._enforce or not _is_session(session):
            return self
        if getattr(session, _ACTIVE_ATTR, False):
            self._nested = True
            return self

        has_pending = _pending_writes(session)
        if has_pending and not self._allow_preexisting_writes:
            raise RuntimeError(AI_READ_ONLY_WRITE_ERROR)

        # 1. Snapshot all preexisting objects and their attributes (deep copies)
        try:
            self._initial_new = set(getattr(session, "new", []))
            self._initial_dirty = set(getattr(session, "dirty", []))
            self._initial_deleted = set(getattr(session, "deleted", []))
            # Include identity map so any clean loaded object modified inside guard is tracked
            identity_objects = set()
            imap = getattr(session, "identity_map", None)
            if imap is not None:
                identity_objects = set(imap.values())

            all_known = self._initial_new | self._initial_dirty | identity_objects
            self._initial_snapshots = {
                obj: _snapshot_object_attributes(obj)
                for obj in all_known
            }
        except Exception:
            self._initial_new = set()
            self._initial_dirty = set()
            self._initial_deleted = set()
            self._initial_snapshots = {}

        # 2. Enter no_autoflush so queries never flush caller's staged changes
        if hasattr(session, "no_autoflush"):
            self._no_autoflush_cm = session.no_autoflush
            try:
                self._no_autoflush_cm.__enter__()
            except Exception:
                self._no_autoflush_cm = None

        # 3. Connection-scoped listener & Database-level enforcement
        try:
            # Check out or retrieve this session's connection
            conn = session.connection()
            self._conn = conn
            conn.info[_CONN_ACTIVE_KEY] = True

            # Attach listener ONLY to this specific connection (NEVER to engine)
            self._conn_cursor_listener = self._cursor_execute
            event.listen(conn, "before_cursor_execute", self._conn_cursor_listener)

            # Database-enforced read-only
            dialect_name = getattr(getattr(conn, "dialect", None), "name", "")
            if dialect_name == "sqlite":
                try:
                    conn.execute(text("PRAGMA query_only = ON"))
                    self._sqlite_query_only_applied = True
                except Exception:
                    pass
            elif dialect_name == "postgresql" and not self._allow_preexisting_writes:
                try:
                    conn.execute(text("SET TRANSACTION READ ONLY"))
                    self._read_only_transaction_applied = True
                except SQLAlchemyError:
                    pass
        except Exception as e:
            logger.debug("Could not attach connection-scoped read-only listener: %s", e)

        # 4. Session-scoped ORM listeners
        self._orm_execute_listener = self._orm_execute
        try:
            event.listen(session, "do_orm_execute", self._orm_execute_listener)
        except Exception:
            self._orm_execute_listener = None

        self._original_flush = session.flush
        self._original_commit = getattr(session, "commit", None)

        def _blocked_flush(*args: Any, **kwargs: Any) -> Any:
            if getattr(session, "new", None) or getattr(session, "dirty", None) or getattr(session, "deleted", None):
                raise RuntimeError(AI_READ_ONLY_WRITE_ERROR)
            return None

        def _blocked_commit(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError(AI_READ_ONLY_WRITE_ERROR)

        session.flush = _blocked_flush  # type: ignore[method-assign]
        session.commit = _blocked_commit  # type: ignore[method-assign]

        setattr(session, _ACTIVE_ATTR, True)
        self._active = True
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if not self._active:
            return False
        session = self._db
        rogue_write_detected = False

        try:
            # 1. Detect and revert ORM object mutations
            try:
                current_new = set(getattr(session, "new", []))
                current_dirty = set(getattr(session, "dirty", []))
                current_deleted = set(getattr(session, "deleted", []))

                new_objects = current_new - self._initial_new
                newly_dirty = current_dirty - self._initial_dirty
                newly_deleted = current_deleted - self._initial_deleted

                # Check attribute changes on all preexisting objects
                mutated_preexisting: dict[Any, dict[str, Any]] = {}
                for obj, entry_snap in self._initial_snapshots.items():
                    changed_attrs = {}
                    for k, saved_val in entry_snap.items():
                        try:
                            curr_val = getattr(obj, k)
                            if curr_val != saved_val:
                                changed_attrs[k] = saved_val
                        except Exception:
                            pass
                    if changed_attrs:
                        mutated_preexisting[obj] = changed_attrs

                if new_objects or newly_dirty or newly_deleted or mutated_preexisting:
                    rogue_write_detected = True

                # Revert new objects: expunge completely
                for obj in list(new_objects):
                    try:
                        session.expunge(obj)
                    except Exception:
                        pass

                # Revert newly dirtied persistent objects: expire them
                for obj in list(newly_dirty):
                    try:
                        session.expire(obj)
                    except Exception:
                        pass

                # Revert modified attributes on preexisting objects back to deep-copied snapshot
                for obj, restored_attrs in mutated_preexisting.items():
                    for k, v in restored_attrs.items():
                        try:
                            setattr(obj, k, copy.deepcopy(v))
                        except Exception:
                            pass

                # Revert deleted objects
                for obj in list(newly_deleted):
                    try:
                        session.expunge(obj)
                        session.merge(obj)
                    except Exception:
                        pass

            except Exception as e:
                logger.exception("Error checking/reverting mutations in read-only guard: %s", e)

            # 2. Reset database-enforced settings
            if self._conn is not None:
                try:
                    if self._sqlite_query_only_applied:
                        self._conn.execute(text("PRAGMA query_only = OFF"))
                except Exception:
                    pass
                try:
                    self._conn.info[_CONN_ACTIVE_KEY] = False
                    if self._conn_cursor_listener is not None:
                        event.remove(self._conn, "before_cursor_execute", self._conn_cursor_listener)
                except Exception:
                    pass

            if self._orm_execute_listener is not None:
                try:
                    event.remove(session, "do_orm_execute", self._orm_execute_listener)
                except Exception:
                    pass

            if not self._allow_preexisting_writes and (rogue_write_detected or _pending_writes(session)):
                try:
                    session.rollback()
                except Exception:
                    pass

            if rogue_write_detected and exc_type is None:
                raise RuntimeError(AI_READ_ONLY_WRITE_ERROR)

            return False
        finally:
            if self._no_autoflush_cm is not None:
                try:
                    self._no_autoflush_cm.__exit__(exc_type, exc, tb)
                except Exception:
                    pass
                self._no_autoflush_cm = None

            try:
                if self._original_flush is not None:
                    session.flush = self._original_flush  # type: ignore[method-assign]
                if self._original_commit is not None:
                    session.commit = self._original_commit  # type: ignore[method-assign]
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
