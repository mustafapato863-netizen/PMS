"""Durable evaluation lifecycle identity for shared dashboard cache keys."""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


def evaluation_cache_identity(db: Session) -> str:
    """Read small history tables, not the employee roster, before cache lookup.

    A committed approval, apply or rollback changes this identity even when a
    Redis version bump is unavailable or another worker has a stale local bump.
    Legacy databases without monthly settings keep their existing cache path.
    The digest contains no user-visible configuration or employee information.
    """
    connection = db.connection()
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    state = []
    if "team_configuration_versions" in tables:
        columns = {column["name"] for column in inspector.get_columns("team_configuration_versions")}
        if "performance_level" in columns:
            row = connection.execute(text(
                "SELECT count(*) AS count, max(published_at) AS published_at "
                "FROM team_configuration_versions WHERE performance_level IS NOT NULL "
                "AND status IN ('approved', 'superseded')"
            )).one()
            # Approvals are immutable and retained. A new approval increments
            # the sealed-history count; draft edits do not affect dashboards.
            state.append(("approved", row.count, str(row.published_at)))
    if "evaluation_revisions" in tables:
        state.extend(
            ("revision", row.status, row.count, str(row.created_at))
            for row in connection.execute(text(
                "SELECT status, count(*) AS count, max(created_at) AS created_at "
                "FROM evaluation_revisions GROUP BY status ORDER BY status"
            ))
        )
    return hashlib.sha256(json.dumps(state, separators=(",", ":")).encode()).hexdigest()
