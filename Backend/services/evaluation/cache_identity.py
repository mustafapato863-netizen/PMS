"""Durable evaluation lifecycle identity for shared dashboard cache keys."""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


def evaluation_cache_identity(db: Session) -> str:
    """Read small history tables, not the employee roster, before cache lookup.

    A committed approval, apply, rollback or workbook replacement changes this
    identity even when a Redis version bump is unavailable or stale. Workbook
    logs are reused by team/month, so counting logs or their original upload
    timestamps alone would miss a replacement. No employee roster is scanned.
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
    if "upload_log" in tables:
        columns = {column["name"] for column in inspector.get_columns("upload_log")}
        # Older installations lack batch_id; do not invent a batch identity.
        fields = [name for name in ("id", "batch_id", "team_id", "year", "month", "status", "record_count") if name in columns]
        if "id" in fields:
            uploads = hashlib.sha256()
            # Identifiers come exclusively from this fixed column allowlist.
            result = connection.execute(text(
                f"SELECT {', '.join(fields)} FROM upload_log ORDER BY id"
            ))
            for row in result:
                uploads.update(json.dumps(tuple(row), default=str, separators=(",", ":")).encode())
                uploads.update(b"\n")
            state.append(("uploads", uploads.hexdigest()))
    return hashlib.sha256(json.dumps(state, separators=(",", ":")).encode()).hexdigest()
