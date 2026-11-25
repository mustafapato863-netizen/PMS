"""Shared, scope-safe, versioned response cache helpers for heavy read endpoints.

Mirrors the cache-key discipline of ``PerformanceDashboardReadService``:
- Keys are SHA-256 digests so no PII or scope identifiers leak into Redis keys.
- Scope isolation uses ``canonical_scope_identity(scope)``.
- Freshness combines ``data_version``, ``config_version``, and
  ``evaluation_cache_identity(db)`` so uploads, approvals, rollbacks, and
  revisions invalidate cached responses automatically across workers.
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Any

from fastapi import Response
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from services.cache_invalidation_service import CacheInvalidationService
from services.cache_service import CacheService
from services.evaluation.cache_identity import evaluation_cache_identity
from utils.report_scope import canonical_scope_identity

RESPONSE_CACHE_ENABLED = True
DEFAULT_RESPONSE_TTL_SECONDS = 180
DEFAULT_PRIVATE_MAX_AGE_SECONDS = 60


def jittered_ttl(seconds: int = DEFAULT_RESPONSE_TTL_SECONDS) -> int:
    """Apply ±10% jitter to avoid synchronized cache stampedes."""
    return max(1, int(round(seconds * random.uniform(0.9, 1.1))))


def _sqlite_memory_fingerprint(db: Session) -> str | None:
    """Isolate ephemeral in-memory SQLite test databases without touching production Postgres."""
    bind = db.get_bind()
    url = str(getattr(bind, "url", "") or "")
    if "sqlite" not in url.lower() or ":memory:" not in url.lower():
        return None
    connection = db.connection()
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    parts: list[Any] = [id(bind)]
    for table_name in ("performance_records", "management_bsc_records", "management_bsc_entries", "teams"):
        if table_name not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "updated_at" in columns:
            row = connection.execute(
                text(f"SELECT count(*) AS c, max(updated_at) AS m FROM {table_name}")
            ).one()
            parts.append((table_name, row.c, str(row.m)))
        else:
            row = connection.execute(text(f"SELECT count(*) AS c FROM {table_name}")).one()
            parts.append((table_name, row.c))
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def build_scoped_response_cache_key(
    db: Session,
    *,
    namespace: str,
    scope: dict,
    params: dict[str, Any],
    schema_version: int = 1,
) -> str:
    """Build a deterministic, scope- and version-isolated cache key."""
    payload: dict[str, Any] = {
        "schema_version": schema_version,
        "namespace": namespace,
        "scope": canonical_scope_identity(scope),
        "params": params,
        "data_version": CacheInvalidationService.get_data_version(),
        "config_version": CacheInvalidationService.get_config_version(),
        "evaluation_identity": evaluation_cache_identity(db),
    }
    sqlite_fp = _sqlite_memory_fingerprint(db)
    if sqlite_fp is not None:
        payload["sqlite_memory"] = sqlite_fp
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
    return f"pms:v1:response:{namespace}:{digest}"


def read_cached_response(key: str, *, cache_type: str) -> Any | None:
    if not RESPONSE_CACHE_ENABLED:
        return None
    return CacheService.get_json(key, cache_type=cache_type)


def write_cached_response(
    key: str,
    value: Any,
    *,
    cache_type: str,
    ttl_seconds: int = DEFAULT_RESPONSE_TTL_SECONDS,
) -> None:
    if not RESPONSE_CACHE_ENABLED:
        return
    CacheService.set_json(key, value, ttl=jittered_ttl(ttl_seconds), cache_type=cache_type)


def apply_private_cache_headers(
    response: Response | None,
    *,
    hit: bool,
    max_age: int = DEFAULT_PRIVATE_MAX_AGE_SECONDS,
) -> None:
    """Attach private-only HTTP cache headers and diagnostic X-Cache status."""
    if response is None:
        return
    response.headers["Cache-Control"] = f"private, max-age={max_age}"
    response.headers["X-Cache"] = "HIT" if hit else "MISS"
