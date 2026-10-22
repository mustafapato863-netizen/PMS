"""Chronological month numbers shared by Python ordering and the SQL CASE
(repositories.performance_repository.month_number_sql)."""
from __future__ import annotations

_NAMES = (
    ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"),
    ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"),
    ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"), ("december", "dec"),
)

MONTH_NUMBERS: dict[str, int] = {
    **{name: number for number, names in enumerate(_NAMES, start=1) for name in names},
    **{str(number): number for number in range(1, 13)},
    **{f"{number:02d}": number for number in range(1, 10)},
}


def month_number(value) -> int:
    """1-12 for a month name, abbreviation or number (case/space-insensitive), else 0."""
    return MONTH_NUMBERS.get(str(value or "").strip(" \t\r\n\f\v").casefold(), 0)
