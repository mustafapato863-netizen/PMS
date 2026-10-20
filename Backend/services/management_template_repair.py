"""Deterministic repair for the management template workbook.

The transform is the only place the five sheet bugs are corrected. Import and
tests call ``repair_workbook``; they do not reimplement the row rules.
"""
from __future__ import annotations

import io
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook

DATA_SHEET = "KPI's Data"
CONFIG_SHEET = "KPI Config"
SOURCE_SHEET = "New Temp"

DATA_TEXT_COLUMNS = (1, 2, 3, 4, 5, 7, 8, 9, 12, 14)
CONFIG_TEXT_COLUMNS = (1, 2, 3, 4, 5, 6, 7, 9)
WEIGHT_TOLERANCE = 0.011

MONTH_NUMBERS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

HIGHER = "Higher is Better"
LOWER = "Lower is Better"


def repair_workbook(path: str | Path) -> dict[str, Any]:
    """Repair ``path`` in place and return a short count of what changed."""
    source = Path(path)
    values = load_workbook(source, data_only=True)
    editable = load_workbook(source, data_only=False)
    report = _repair_loaded(values, editable)
    editable.save(source)
    values.close()
    editable.close()
    return report


def repair_workbook_bytes(contents: bytes) -> bytes:
    """Repair a management template in memory.

    Workbooks that are not the three-sheet management template are returned
    unchanged so an ordinary scorecard upload still parses as before.
    """
    try:
        workbook = load_workbook(io.BytesIO(contents), data_only=False)
    except Exception:
        return contents
    try:
        names = set(workbook.sheetnames)
    finally:
        workbook.close()
    if not {DATA_SHEET, CONFIG_SHEET, SOURCE_SHEET} <= names:
        return contents

    temporary = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    temporary_path = Path(temporary.name)
    try:
        temporary.write(contents)
        temporary.close()
        repair_workbook(temporary_path)
        return temporary_path.read_bytes()
    finally:
        temporary_path.unlink(missing_ok=True)


def _repair_loaded(values: Workbook, editable: Workbook) -> dict[str, Any]:
    data_values = values[DATA_SHEET]
    source_values = values[SOURCE_SHEET]
    data_edit = editable[DATA_SHEET]
    config_edit = editable[CONFIG_SHEET]
    source_edit = editable[SOURCE_SHEET]

    _strip_sheet(data_edit, DATA_TEXT_COLUMNS)
    _strip_sheet(config_edit, CONFIG_TEXT_COLUMNS)
    _strip_sheet(source_edit, DATA_TEXT_COLUMNS)
    removed_config = _remove_duplicate_config_rows(config_edit)

    rows = [_read_data_row(data_values, data_edit, number) for number in range(2, data_values.max_row + 1)]
    rows = [row for row in rows if row["code"] or row["kpi"]]
    source_rows = [_read_source_row(source_values, number) for number in range(2, source_values.max_row + 1)]
    source_rows = [row for row in source_rows if row["code"] or row["kpi"]]
    aligned = _align_source_block(rows, source_rows)
    for index in aligned:
        source_row = source_rows[aligned[index]]
        row = rows[index]
        if source_row["period"] is not None:
            row["period"] = source_row["period"]
            row["period_from_source"] = True
        if source_row["weight"] is not None:
            row["weight"] = source_row["weight"]
            row["weight_from_source"] = True
        # New Temp's score is the achievement the reversed direction has to match.
        # The data sheet's score was calculated from the wrong direction.
        row["source_actual"] = source_row["actual"]
        row["source_target"] = source_row["target"]
        row["source_score"] = source_row["score"]

    config_weights = _config_weight_lookup(config_edit)
    _apply_scoped_weights(rows, config_weights)
    deleted = _drop_incomplete_subset_blocks(rows)
    _apply_directions(rows, config_edit)

    for row in rows:
        cell_row = row["number"]
        if row["period"] is not None:
            data_edit.cell(cell_row, 6).value = datetime(row["period"].year, row["period"].month, row["period"].day)
        if row["weight"] is not None:
            data_edit.cell(cell_row, 10).value = row["weight"]
        if row["direction"]:
            data_edit.cell(cell_row, 9).value = row["direction"]
        _widen_score_formula(data_edit.cell(cell_row, 15))

    delete_numbers = sorted(deleted, reverse=True)
    for number in delete_numbers:
        data_edit.delete_rows(number, 1)
    _shrink_table(data_edit, len(delete_numbers))

    return {
        "aligned_rows": len(aligned),
        "deleted_rows": len(deleted),
        "removed_config_rows": removed_config,
        "data_rows": len(rows),
    }


def _strip_sheet(sheet, columns: tuple[int, ...]) -> None:
    for row in sheet.iter_rows(min_row=2, max_row=sheet.max_row, max_col=max(columns)):
        for cell in row:
            if cell.column not in columns or not isinstance(cell.value, str):
                continue
            stripped = cell.value.strip()
            if stripped != cell.value:
                cell.value = stripped


def _remove_duplicate_config_rows(sheet) -> int:
    seen: set[tuple[str, str, str, str]] = set()
    remove: list[int] = []
    for number in range(2, sheet.max_row + 1):
        key = (
            _text(sheet.cell(number, 1).value).casefold(),
            _text(sheet.cell(number, 2).value).casefold(),
            _text(sheet.cell(number, 4).value).casefold(),
            _text(sheet.cell(number, 6).value).casefold(),
        )
        if not any(key):
            continue
        if key in seen:
            remove.append(number)
            continue
        seen.add(key)
    for number in reversed(remove):
        sheet.delete_rows(number, 1)
    return len(remove)


def _read_data_row(values_sheet, edit_sheet, number: int) -> dict[str, Any]:
    code = _employee_code(values_sheet.cell(number, 1).value)
    kpi = _text(values_sheet.cell(number, 8).value)
    return {
        "number": number,
        "code": code,
        "team": _text(values_sheet.cell(number, 2).value),
        "position": _text(values_sheet.cell(number, 4).value),
        "level": _text(values_sheet.cell(number, 5).value),
        "period": _as_date(values_sheet.cell(number, 6).value) or _month_start(_text(values_sheet.cell(number, 6).value)),
        "kpi": kpi,
        "direction": _canonical_direction(values_sheet.cell(number, 9).value),
        "weight": _weight(values_sheet.cell(number, 10).value),
        "original_weight": _weight(values_sheet.cell(number, 10).value),
        "target": _number(values_sheet.cell(number, 11).value),
        "actual": _number(values_sheet.cell(number, 13).value),
        "score": _score(values_sheet.cell(number, 15).value),
        "period_from_source": False,
        "weight_from_source": False,
        "edit_direction_is_formula": isinstance(edit_sheet.cell(number, 9).value, str)
        and str(edit_sheet.cell(number, 9).value).startswith("="),
    }


def _read_source_row(sheet, number: int) -> dict[str, Any]:
    return {
        "code": _employee_code(sheet.cell(number, 1).value),
        "kpi": _text(sheet.cell(number, 8).value),
        "period": _month_start(sheet.cell(number, 6).value),
        "weight": _weight(sheet.cell(number, 10).value),
        "target": _number(sheet.cell(number, 11).value),
        "actual": _number(sheet.cell(number, 13).value),
        "score": _score(sheet.cell(number, 15).value),
    }


def _align_source_block(rows: list[dict[str, Any]], source_rows: list[dict[str, Any]]) -> dict[int, int]:
    if not source_rows:
        return {}
    data_keys = [(_lookup(row["code"]), _lookup(row["kpi"])) for row in rows]
    source_keys = [(_lookup(row["code"]), _lookup(row["kpi"])) for row in source_rows]
    width = len(source_keys)
    start = None
    for index in range(0, len(data_keys) - width + 1):
        if data_keys[index:index + width] == source_keys:
            start = index
    if start is None:
        return {}
    return {start + offset: offset for offset in range(width)}


def _config_weight_lookup(sheet) -> dict[tuple[str, str, str, str], float]:
    lookup: dict[tuple[str, str, str, str], float] = {}
    for number in range(2, sheet.max_row + 1):
        weight = _weight(sheet.cell(number, 8).value)
        if weight is None:
            continue
        lookup[(
            _lookup(sheet.cell(number, 1).value),
            _lookup(sheet.cell(number, 2).value),
            _lookup(sheet.cell(number, 4).value),
            _lookup(sheet.cell(number, 6).value),
        )] = weight
    return lookup


def _apply_scoped_weights(rows: list[dict[str, Any]], lookup: dict[tuple[str, str, str, str], float]) -> None:
    """Replace KPI-only lookup weights. A month that already sums to 100% is kept."""
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for row in rows:
        if row["weight_from_source"]:
            continue
        key = (
            _lookup(row["team"]),
            _lookup(row["position"]),
            _lookup(row["level"]),
            _lookup(row["kpi"]),
        )
        if key in lookup:
            row["proposed_weight"] = lookup[key]
        groups.setdefault(_month_group(row), []).append(row)

    for group in groups.values():
        proposed = [row.get("proposed_weight", row["weight"]) or 0.0 for row in group]
        original = [row["original_weight"] or 0.0 for row in group]
        if _near_one(sum(proposed)) or not _near_one(sum(original)):
            for row, weight in zip(group, proposed):
                row["weight"] = weight
        # Otherwise the stored month already sums to 100%; keep those weights.


def _drop_incomplete_subset_blocks(rows: list[dict[str, Any]]) -> list[int]:
    """Drop an employee-month whose KPIs are a strict subset of a fuller month and do not sum to 100%."""
    grouped: dict[tuple[str, str, date | None], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_month_group(row), []).append(row)
    by_person: dict[tuple[str, str], list[tuple[date | None, set[str], float]]] = {}
    for (code, position, period), group in grouped.items():
        names = {_lookup(row["kpi"]) for row in group if row["kpi"]}
        total = sum(row["weight"] or 0.0 for row in group)
        by_person.setdefault((code, position), []).append((period, names, total))

    remove: list[int] = []
    for (code, position, period), group in grouped.items():
        names = {_lookup(row["kpi"]) for row in group if row["kpi"]}
        total = sum(row["weight"] or 0.0 for row in group)
        if _near_one(total) or not names:
            continue
        fuller = any(
            other_period != period and names < other_names
            for other_period, other_names, _other_total in by_person[(code, position)]
        )
        if fuller:
            remove.extend(row["number"] for row in group)
            for row in group:
                row["deleted"] = True
    rows[:] = [row for row in rows if not row.get("deleted")]
    return remove


def _apply_directions(rows: list[dict[str, Any]], config_sheet) -> None:
    for row in rows:
        actual = row["source_actual"] if row.get("source_actual") is not None else row["actual"]
        target = row["source_target"] if row.get("source_target") is not None else row["target"]
        score = row["source_score"] if row.get("source_score") is not None else row["score"]
        chosen = _direction_for_measurement(actual, target, score, row["direction"])
        forced = _forced_direction(row["team"], row["position"], row["kpi"])
        if forced and row["kpi"].casefold() != "average ticket resolution time":
            chosen = forced
        row["direction"] = chosen or row["direction"] or HIGHER

    for number in range(2, config_sheet.max_row + 1):
        team = _text(config_sheet.cell(number, 1).value)
        position = _text(config_sheet.cell(number, 2).value)
        kpi = _text(config_sheet.cell(number, 6).value)
        current = _canonical_direction(config_sheet.cell(number, 7).value)
        forced = _forced_direction(team, position, kpi)
        if kpi.casefold() == "average ticket resolution time":
            forced = HIGHER
        if forced:
            config_sheet.cell(number, 7).value = forced
        elif current:
            config_sheet.cell(number, 7).value = current


def _forced_direction(team: str, position: str, kpi: str) -> str | None:
    label = kpi.casefold()
    if label == "schedule variance" and "offshore admin" in team.casefold():
        return HIGHER
    if label == "team shrinkage" and "team leader" in position.casefold():
        return LOWER
    return None


def _direction_for_measurement(actual: float | None, target: float | None, score: float | None, current: str | None) -> str | None:
    if actual is None or target is None or score is None:
        return current
    higher = _achievement("higher", actual, target)
    lower = _achievement("lower", actual, target)
    if higher is None or lower is None:
        return current
    higher_error = abs(higher - score)
    lower_error = abs(lower - score)
    if higher_error <= 0.02 and higher_error + 0.02 < lower_error:
        return HIGHER
    if lower_error <= 0.02 and lower_error + 0.02 < higher_error:
        return LOWER
    return current


def _achievement(direction: str, actual: float, target: float) -> float | None:
    if direction == "lower":
        if actual == 0:
            return 0.0
        return min(1.0, target / actual)
    if target == 0:
        return 0.0
    return min(1.0, actual / target)


def _widen_score_formula(cell) -> None:
    """The stored formula matches only ``Lower Better``. Accept the repaired phrase too."""
    formula = cell.value
    if not isinstance(formula, str):
        return
    needle = f'I{cell.row}="Lower Better"'
    replacement = f'OR(I{cell.row}="Lower Better",I{cell.row}="Lower is Better")'
    if needle in formula and "Lower is Better" not in formula:
        cell.value = formula.replace(needle, replacement, 1)


def _shrink_table(sheet, deleted_rows: int) -> None:
    if deleted_rows <= 0 or not getattr(sheet, "tables", None):
        return
    for name in list(sheet.tables):
        table = sheet.tables[name]
        ref = getattr(table, "ref", table)
        if not isinstance(ref, str) or ":" not in ref:
            continue
        start, end = ref.split(":")
        end_row = int("".join(character for character in end if character.isdigit()) or "0")
        end_col = "".join(character for character in end if character.isalpha())
        updated = f"{start}:{end_col}{max(1, end_row - deleted_rows)}"
        if hasattr(table, "ref"):
            table.ref = updated


def _month_group(row: dict[str, Any]) -> tuple[str, str, date | None]:
    return (_lookup(row["code"]), _lookup(row["position"]), row["period"])


def _near_one(total: float) -> bool:
    return abs(total - 1.0) <= WEIGHT_TOLERANCE


def _employee_code(value: Any) -> str:
    text = _text(value)
    if text.endswith(".0"):
        text = text[:-2]
    compact = text.replace(" ", "")
    if compact.isdigit():
        return f"SGHD{compact}"
    return compact.upper()


def _lookup(value: Any) -> str:
    return _text(value).casefold()


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _month_start(value: Any) -> date | None:
    parsed = _as_date(value)
    if parsed is not None:
        return date(parsed.year, parsed.month, 1)
    text = _text(value).casefold()
    if not text:
        return None
    month = MONTH_NUMBERS.get(text) or MONTH_NUMBERS.get(text[:3])
    if month is None:
        return None
    return date(2026, month, 1)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _text(value).replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _weight(value: Any) -> float | None:
    if isinstance(value, str) and value.strip().lower() == "view":
        return 0.0001
    number = _number(value)
    if number is None:
        return None
    if number > 1:
        return number / 100.0
    return number


def _score(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    if abs(number) > 2:
        return number / 100.0
    return number


def _canonical_direction(value: Any) -> str | None:
    text = _text(value).casefold().replace(" ", "")
    if "lower" in text:
        return LOWER
    if "higher" in text:
        return HIGHER
    return None


