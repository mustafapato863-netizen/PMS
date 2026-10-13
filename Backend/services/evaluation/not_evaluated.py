"""Not-evaluated employee-months: rows the business deliberately does not score.

A row is NOT EVALUATED when BOTH hold:

1. its workbook status says leave, inactive or new (a case-insensitive whole-word
   match on the Status text: "Leave", "On leave", "Inactive", "New", "Active - New"),
   and
2. ANY weighted KPI actual is missing. A missing actual is a blank cell, NaN, or a
   non-numeric marker ("-", "–", "—", "N/A", "NA", "n/a"). A new employee's
   rejection rate is a dash in the workbook, so a partly filled row counts.

Such a row is not scored by the approved basis and never raises for missing
evidence. It keeps exactly what the legacy upload path stores. A row with an
evaluated status (Active and anything else) is never not-evaluated: any missing
weighted actual still blocks, with the existing "is missing" message. A status row
with every weighted actual present is scored normally.

Markers are normalised to a missing actual where the evidence is read, before any
number is parsed (``normalise_actual_cells``). ``_source_number`` keeps its contract:
a genuinely malformed number such as "12abc" still raises ``invalid_evidence``.

This module is the one definition. Callers decide "not evaluated" before the
scorer runs. The scorer itself and ``_missing_actual`` are unchanged.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

_STATUS_WORD = re.compile(r"\b(leave|inactive|new)\b", re.IGNORECASE)
_LABELS = {"leave": "on leave", "inactive": "inactive", "new": "new"}
# Workbook text that stands for "no actual" in an actual cell (compared case-insensitively).
MISSING_MARKERS = frozenset({"-", "–", "—", "n/a", "na"})


def status_label(status_text: Any) -> str | None:
    """'on leave', 'inactive' or 'new' when the Status text names one of them, else None."""
    if not isinstance(status_text, str):
        return None
    match = _STATUS_WORD.search(status_text)
    return _LABELS[match.group(1).casefold()] if match else None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return not (isinstance(value, float) and math.isnan(value)) and value != 0
    return str(value or "").strip().casefold() in {"true", "yes", "1"}


def status_evidence(raw: Mapping[str, Any] | None) -> str | None:
    """Status label from the workbook row kept in ``raw_data``.

    The Status text decides when it is present. The cleaner's Is_Inactive and
    Is_New flags are used only when the row has no Status text. The record's own
    performance ``status`` column (Exceeds, Meets, Below) is not workbook status
    and is never used. No usable evidence gives None, which keeps the row strict.
    """
    if not isinstance(raw, Mapping):
        return None
    status = raw.get("Status")
    if isinstance(status, str) and status.strip():
        return status_label(status)
    if _truthy(raw.get("Is_Inactive")):
        return "inactive"
    if _truthy(raw.get("Is_New")):
        return "new"
    return None


def weighted_keys(lines: Iterable[Mapping[str, Any]]) -> list[str]:
    """KPI keys with a positive weight in the approved basis. A weight-0 KPI does not count."""
    keys = []
    for line in lines:
        try:
            weight = Decimal(str(line.get("weight"))) if line.get("weight") not in (None, "") else Decimal("0")
        except (InvalidOperation, ValueError):
            weight = Decimal("0")
        if weight > 0:
            keys.append(str(line.get("kpi_key")))
    return keys


def is_missing_actual(value: Any) -> bool:
    """True for a blank cell, NaN, or a non-numeric marker. Anything else is left to the parser."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str):
        text = value.strip()
        return text == "" or text.casefold() in MISSING_MARKERS
    return False


def actuals_by_key(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Actual per KPI key from scoring rows (``actual`` or ``actual_value``)."""
    values: dict[str, Any] = {}
    for row in rows:
        key = str(row.get("kpi_key"))
        value = row.get("actual") if "actual" in row else row.get("actual_value")
        values[key] = value
    return values


def missing_weighted_keys(lines: Iterable[Mapping[str, Any]], actuals: Mapping[str, Any]) -> list[str]:
    """Weighted KPI keys whose actual is missing. Absent keys count as missing."""
    return [key for key in weighted_keys(lines) if is_missing_actual(actuals.get(key))]


def not_evaluated_reason(
    lines: Iterable[Mapping[str, Any]],
    actuals: Mapping[str, Any],
    raw: Mapping[str, Any] | None,
) -> str | None:
    """The status label when the row is NOT EVALUATED, else None.

    ``actuals`` maps each KPI key to its actual (None or a marker when missing).
    A status row with ANY weighted actual missing is not evaluated. With all of
    them present it is scored normally. An evaluated status is never not-evaluated.
    """
    label = status_evidence(raw)
    if label is None:
        return None
    if not weighted_keys(lines):
        return None
    return label if missing_weighted_keys(lines, actuals) else None


def _cell_key(raw: Mapping[str, Any], column: str) -> str | None:
    """The raw key that holds ``column``. Same match rule as the workflow's cell lookup."""
    if column in raw:
        return column
    wanted = "".join(character for character in str(column).casefold() if character.isalnum())
    if not wanted:
        return None
    for key in raw:
        if "".join(character for character in str(key).casefold() if character.isalnum()) == wanted:
            return key
    return None


def normalise_actual_cells(config: Mapping[str, Any] | None, raw: Any) -> Any:
    """Copy of a workbook row in which every KPI actual cell that is a missing marker is None.

    Only the configured actual columns change. Target columns and other cells are
    left as they are. Returns ``raw`` unchanged when there is no row or no config.
    """
    if not isinstance(raw, Mapping) or not isinstance(config, Mapping):
        return raw
    normalised = dict(raw)
    for kpi in config.get("kpis") or []:
        if not isinstance(kpi, Mapping) or not kpi.get("actual_col"):
            continue
        key = _cell_key(normalised, str(kpi["actual_col"]))
        if key is not None and is_missing_actual(normalised[key]):
            normalised[key] = None
    return normalised


def reason_text(label: str, missing: Iterable[str] | None = None, weighted: Iterable[str] | None = None) -> str:
    """Per-row reason shown in the upload result, the warnings and the impact proof.

    "no actuals" when every weighted actual is missing, otherwise the missing KPIs.
    """
    missing_list = list(missing or [])
    weighted_list = list(weighted or [])
    if not missing_list or (weighted_list and set(missing_list) >= set(weighted_list)):
        return f"Not evaluated: {label}, no actuals"
    return f"Not evaluated: {label}, actual missing for {', '.join(missing_list)}"
