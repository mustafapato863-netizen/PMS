"""Keep the workbook's raw numeric serial for known percent columns.

Excel builtin format 22 (``m/d/yy h:mm``) makes a date-aware reader turn the
serial 0.65 into 15:36. The cell's stored number is still 0.65. For columns
declared as percent units, that serial is the ratio. This reader copies the
worksheet ``<v>`` number and does not convert a time of day or divide by 100.
Date and time columns that are not in the known set are left alone.
"""

from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree

import pandas as pd

from services.outbound_period_basis import is_known_percent_column


_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def restore_known_percent_serials(frame: pd.DataFrame, source, sheet_name: str) -> pd.DataFrame:
    """Replace known percent cells with the workbook numeric serial."""
    if frame is None or frame.empty:
        return frame
    serials = _raw_percent_serials(source, sheet_name, list(frame.columns))
    if not serials:
        return frame
    restored = frame.copy()
    for column, values in serials.items():
        if column not in restored.columns:
            continue
        restored[column] = restored[column].astype(object)
        for index, number in values.items():
            if 0 <= index < len(restored):
                restored.iat[index, restored.columns.get_loc(column)] = number
    return restored


def _raw_percent_serials(source, sheet_name: str, columns: list) -> dict:
    blob = _open_zip(source)
    if blob is None:
        return {}
    try:
        with zipfile.ZipFile(blob) as workbook:
            sheet_path = _worksheet_path(workbook, sheet_name)
            if sheet_path is None or sheet_path not in workbook.namelist():
                return {}
            shared = _shared_strings(workbook)
            root = ElementTree.fromstring(workbook.read(sheet_path))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, OSError):
        return {}

    header_by_column: dict[int, str] = {}
    values: dict[str, dict[int, float]] = {}
    column_by_norm = {}
    for column in columns:
        if is_known_percent_column(column):
            column_by_norm[_norm(column)] = column

    for row in root.iter(f"{_MAIN}row"):
        row_number = _int(row.attrib.get("r"))
        if row_number is None:
            continue
        for cell in row.findall(f"{_MAIN}c"):
            column_index = _column_index(cell.attrib.get("r"))
            if column_index is None:
                continue
            if row_number == 1:
                header = _cell_text(cell, shared)
                if header is not None:
                    header_by_column[column_index] = header
                continue
            header = header_by_column.get(column_index)
            if header is None or not is_known_percent_column(header):
                continue
            target = column_by_norm.get(_norm(header))
            if target is None:
                continue
            number = _numeric_value(cell)
            if number is None:
                continue
            values.setdefault(target, {})[row_number - 2] = number
    return values


def _shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall(f"{_MAIN}si"):
        strings.append("".join(text.text or "" for text in item.iter(f"{_MAIN}t")))
    return strings


def _cell_text(cell, shared: list[str]) -> str | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.iter(f"{_MAIN}t")) or None
    node = cell.find(f"{_MAIN}v")
    if node is None or node.text is None:
        return None
    if cell_type == "s":
        try:
            return shared[int(node.text)]
        except (ValueError, IndexError):
            return None
    if cell_type in {None, "n"}:
        return None
    return node.text


def _numeric_value(cell) -> float | None:
    cell_type = cell.attrib.get("t")
    if cell_type not in {None, "n"}:
        return None
    node = cell.find(f"{_MAIN}v")
    if node is None or node.text is None:
        return None
    try:
        return float(node.text)
    except ValueError:
        return None


def _worksheet_path(workbook: zipfile.ZipFile, sheet_name: str) -> str | None:
    try:
        workbook_root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
        rels_root = ElementTree.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    except KeyError:
        return None
    relation_id = None
    for sheet in workbook_root.iter(f"{_MAIN}sheet"):
        if sheet.attrib.get("name") == sheet_name:
            relation_id = sheet.attrib.get(f"{_REL}id")
            break
    if relation_id is None:
        return None
    target = None
    for rel in rels_root:
        if rel.attrib.get("Id") == relation_id:
            target = rel.attrib.get("Target")
            break
    if not target:
        return None
    target = target.lstrip("/")
    if not target.startswith("xl/"):
        target = "xl/" + target
    return target


def _open_zip(source):
    if isinstance(source, (bytes, bytearray)):
        return io.BytesIO(source)
    if isinstance(source, pd.ExcelFile):
        handle = getattr(source, "_io", None)
        if isinstance(handle, (bytes, bytearray)):
            return io.BytesIO(handle)
        if isinstance(handle, str):
            return handle
        if handle is not None and hasattr(handle, "seek") and hasattr(handle, "read"):
            handle.seek(0)
            payload = handle.read()
            handle.seek(0)
            return io.BytesIO(payload)
        path = getattr(source, "io", None)
        if isinstance(path, str):
            return path
    if isinstance(source, str):
        return source
    if hasattr(source, "seek") and hasattr(source, "read"):
        source.seek(0)
        return source
    return None


def _column_index(reference: str | None) -> int | None:
    if not reference:
        return None
    letters = []
    for char in reference:
        if char.isalpha():
            letters.append(char.upper())
        else:
            break
    if not letters:
        return None
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index - 1


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _norm(value) -> str:
    return "".join(char.lower() for char in str(value or "") if not char.isspace())
