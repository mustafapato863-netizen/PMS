"""Read-time detection of duplicate performance rows that differ only by employee-ID spelling.

Real data (Nov 27 2026): 103 employee rows are exact twins of another row, same person, period, team,
region and score, stored once as "SGHD70136" and once as bare "70136". They double count in headcount
and team averages. This module only DECIDES which rows to hide; nothing is rewritten or deleted.

Rule (deliberately narrow): a bare-digits row is a twin when the same (period, team, level) also has a
prefixed row ("SGH" + one letter + same digits) with the same normalized name AND the same score.
Numeric IDs shared by different people under other prefixes are never merged.
"""
from __future__ import annotations

import os
import re
from decimal import Decimal
from typing import Any, Iterable

_BARE = re.compile(r"\d+")
_PREFIXED = re.compile(r"SGH[A-Z](\d+)", re.IGNORECASE)
_TRUTHY = {"1", "true", "yes", "on", "enabled"}


def exclude_id_twins_enabled() -> bool:
    return os.environ.get("PMS_EXCLUDE_ID_TWINS", "").strip().casefold() in _TRUTHY


def normalize_name(name: Any) -> str:
    """Collapse internal whitespace and fold case, for matching only (never for display)."""
    return " ".join(str(name or "").split()).casefold()


def _score_key(score: Any) -> str:
    try:
        return str(Decimal(str(score)).quantize(Decimal("0.01")))
    except Exception:
        return str(score)


def find_id_twin_rows(rows: Iterable[Any]) -> list[Any]:
    """Return the ``key`` of each bare-ID row that has an identical prefixed twin.

    Each row is a mapping or object with: key (opaque, returned as is), employee_id, name, year, month,
    team_id, level, score.
    """
    def get(row: Any, field: str) -> Any:
        return row[field] if isinstance(row, dict) else getattr(row, field)

    groups: dict[tuple, dict[str, list[Any]]] = {}
    for row in rows:
        emp = str(get(row, "employee_id") or "").strip()
        digits = None
        kind = None
        if _BARE.fullmatch(emp):
            digits, kind = emp, "bare"
        else:
            m = _PREFIXED.fullmatch(emp)
            if m:
                digits, kind = m.group(1), "prefixed"
        if digits is None:
            continue
        gkey = (digits, get(row, "year"), str(get(row, "month")).strip().casefold(), get(row, "team_id"), str(get(row, "level")).casefold())
        groups.setdefault(gkey, {"bare": [], "prefixed": []})[kind].append(row)
    excluded = []
    for g in groups.values():
        if not g["bare"] or not g["prefixed"]:
            continue
        for b in g["bare"]:
            if any(
                normalize_name(get(b, "name")) == normalize_name(get(p, "name"))
                and _score_key(get(b, "score")) == _score_key(get(p, "score"))
                for p in g["prefixed"]
            ):
                excluded.append(get(b, "key"))
    return excluded
