"""One region rule for every path: strip, treat empty as missing, fall back
record -> employee -> team. The SQL twin is
repositories.performance_repository._row_region."""
from __future__ import annotations

# Same set on both sides: SQL trim(x, chars) (SQLite, PostgreSQL 14+) and str.strip(chars).
REGION_WHITESPACE = " \t\r\n\f\v"


def first_region(*values) -> str:
    for value in values:
        normalized = str(value or "").strip(REGION_WHITESPACE)
        if normalized:
            return normalized
    return ""
