"""One region rule for every path: strip, treat empty as missing, fall back
record -> employee -> team. The SQL twin is
repositories.performance_repository._row_region."""
from __future__ import annotations

import re

# Same set on both sides: SQL trim(x, chars) (SQLite, PostgreSQL 14+) and str.strip(chars).
REGION_WHITESPACE = " \t\r\n\f\v"


def first_region(*values) -> str:
    for value in values:
        normalized = str(value or "").strip(REGION_WHITESPACE)
        if normalized:
            return normalized
    return ""


_KSA_HINT_PATTERN = re.compile(
    r"\b(?:ksa|saudi(?:\s+arabia)?|kingdom\s+of\s+saudi\s+arabia)\b",
    re.IGNORECASE,
)


def ksa_region_hint_from_prompt(prompt: str | None) -> str | None:
    """Normalize an explicit Saudi Arabia/KSA mention without altering existing country routing."""
    return "KSA" if _KSA_HINT_PATTERN.search(str(prompt or "")) else None
