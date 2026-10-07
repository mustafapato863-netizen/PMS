"""Canonical branch parsing for access control.

Only explicit source fields are authorization evidence. Booking/attendance geo
totals are deliberately excluded because a single employee can have activity
in more than one branch while the score row itself is not branch-partitioned.
"""

from __future__ import annotations

import re
from typing import Any


BRANCH_KEYS = ("dubai", "sharjah", "ajman", "clinics")
REGION_CODES = ("UAE", "EGY", "Other")

_ALIASES = {
    "dubai": ("DUBAI", "DXB"),
    "sharjah": ("SHARJAH", "SHARQA", "SHJ"),
    "ajman": ("AJMAN", "AJM"),
    "clinics": ("CLINIC", "CLINICS"),
}


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _raw_data(record: Any) -> dict[str, Any]:
    raw = _value(record, "raw_data")
    if isinstance(raw, dict):
        return raw
    payload = _value(record, "record_payload")
    if isinstance(payload, dict) and isinstance(payload.get("raw_data"), dict):
        return payload["raw_data"]
    return {}


def explicit_branch_key(record: Any) -> str | None:
    """Return a unique branch explicitly named in source fields, else ``None``.

    There is intentionally no fallback to region, team assignments, or geo
    activity. Multiple branch markers make a row ambiguous and fail closed.
    """

    raw = _raw_data(record)
    source_values = [
        raw.get("Branch"),
        raw.get("Site"),
        raw.get("Area"),
        raw.get("Out Team"),
        raw.get("Team"),
    ]
    text = " ".join(str(value or "").upper() for value in source_values)
    matches = {
        branch
        for branch, aliases in _ALIASES.items()
        if any(re.search(rf"(?<![A-Z0-9]){re.escape(alias)}(?![A-Z0-9])", text) for alias in aliases)
    }
    return next(iter(matches)) if len(matches) == 1 else None
