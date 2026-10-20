"""Header notices for an upload that has already been read.

Notices use the raw header row only. They do not read employee cells, register
columns, or change a score. The ordinary Outbound template below is the only
workbook header list confirmed for this phase.

Other sheets list a header as unmapped only when no importer step reads it.
A column counts as read when the team configuration names it, when the shared
cleaner or the seeder reads it by name, or when the team's importer declares it
next to its own code (READ_COLUMNS, READ_ANCHORS, READ_PATTERNS). Workbook
layout (the side KPI table, pandas duplicate suffixes such as "Date.1") is never
a data column and is never listed.
"""

from __future__ import annotations

import importlib
import math
import re
from contextvars import ContextVar, Token
from functools import wraps
from typing import Any, Callable, Iterable, Mapping

import pandas as pd

from config.loader import ConfigurationError, load_team_config
from services.outbound_period_basis import (
    PRODUCTIVITY_ACTUAL_ALIASES,
    PRODUCTIVITY_TARGET_ALIASES,
    is_outbound_sheet,
)
from utils.helpers import convert_percentage


MAX_HEADERS_PER_NOTICE = 25
MAX_NOTICES = 12

# Authoritative ordinary Outbound headers, including the spaces in the workbook.
ORDINARY_OUTBOUND_HEADERS = (
    "Date",
    "Region",
    "Role",
    "SGH Code",
    "English Name",
    "Out Team",
    "Num Of Leads",
    "Reached",
    "Not Reached",
    "Trails",
    "Connected",
    "Avail Time",
    "AHT",
    "Dubai _Booking",
    "Sharjah_Booking",
    "Ajman_Booking",
    "Clinics _Booking",
    "Dubai _Attend",
    "Sharjah_Attend",
    "Ajman_Attend",
    "clinics_Attend",
    "A.Booking %",
    "A.Attend %",
    "A.AHT",
    "A.Reachability %",
    "A.Quality Score",
    "T.Booking %",
    "T.Attend %",
    "T.AHT",
    "T.Reachability %",
    "T.Quality Target",
    "Booking C.R Ach%",
    "Attend C.R Ach%",
    "AHT Ach%",
    "Reachability % Ach%",
    "Quality Ach%",
    "Performance Score",
    "Performance Grade",
)

# The configured quality target name. It is not in the ordinary header row.
QUALITY_TARGET_COLUMN = "T.Quality%"
QUALITY_TARGET_ALIAS = "T.Quality Target"

# Columns the outbound processor already keeps or ignores on the template.
OUTBOUND_ESTABLISHED_COLUMNS = (
    "Status",
    "Available Time",
    "EmployeeID",
    "EmployeeName",
    "SGHCode",
    "EnglishName",
    "Utliztion %",
    "Utilization %",
    "A.Utilization%",
    "T.Utilization%",
    "Utilization% Ach",
    "Utilization% Ach%",
    "Score Range",
    "Classification",
    "Grade",
    "Distribution",
)

SHARED_METADATA_COLUMNS = (
    "Date",
    "Region",
    "Role",
    "Status",
    "Team",
    "Position",
    "Workstream",
    "Performance Grade",
    "Performance Score",
    "Employee ID",
    "Employee Name",
    "English Name",
    "Agent Name",
    "HR ID",
)

# Read by the shared cleaner (AHT -> AHT_Minutes) and the seeder (aht_raw, calls and
# geo counts) for every team sheet. A drift test checks that each name still appears
# in cleaned.py or services/seeding_service.py.
SHARED_READ_COLUMNS = (
    "AHT",
    "A.AHT",
    "A.AHT.1",
    "InboundCalls",
    "OutboundCalls",
    "TotalHandledCalls",
    "AbandonedCalls",
    "Dubai_Booking",
    "Sharjah_Booking",
    "Ajman_Booking",
    "Clinics_Booking",
    "clinics_Booking",
    "Dubai_Attend",
    "Sharjah_Attend",
    "Ajman_Attend",
    "Clinics_Attend",
    "clinics_Attend",
    "clinics.Attend",
    "Clinics.Attend",
)

# The cleaner crops every column after this one (preserve_productivity_columns).
GRADE_COLUMN = "Performance Grade"

# Workbook layout around the data table. The side KPI table and its headings are
# not data columns, so they are never listed.
LAYOUT_COLUMNS = (
    "KPI",
    "Weight",
    "Target",
    "Direction",
    "Achievement Score Formula",
    "Weighted Score",
    "Score Range",
    "Classification",
    "Distribution",
)
_LAYOUT_TITLE = re.compile(r"^updatedpre-approvals.*kpitable$")
# pandas renames a repeated header to "<name>.<n>"; the repeat is never read by name.
_DUPLICATE_SUFFIX = re.compile(r"^(?P<base>.+)\.\d+$")

# Team sheet -> the importer module that declares what it reads. Outbound is not
# listed: its template above is the only confirmed header list for that sheet.
_READ_MODULES = {
    "Inbound": "Data_Cleaning_Teams.inbound",
    "Sales": "Data_Cleaning_Teams.sales",
    "Coding": "Data_Cleaning_Teams.coding",
    "CSR": "Data_Cleaning_Teams.csr",
    "Pharmacy": "Data_Cleaning_Teams.pharmacy",
    "Submission": "Data_Cleaning_Teams.submission",
    "Re-Submission": "Data_Cleaning_Teams.re_submission",
    "Pre-Approvals IP Offshore": "Data_Cleaning_Teams.preapprovals_offshore",
    "Pre-Approvals OP Dubai": "Data_Cleaning_Teams.preapprovals_op_dubai",
    "Pre-Approvals IP Final Dubai": "Data_Cleaning_Teams.preapprovals_ip_final_dubai",
    "Pre-Approvals IP Elective Dubai": "Data_Cleaning_Teams.preapprovals_ip_elective_dubai",
    "Pre-Approvals OP Final SHJAJM": "Data_Cleaning_Teams.preapprovals_op_final_shj_ajm",
    "Pre-Approvals IP Final SHJAJM": "Data_Cleaning_Teams.preapprovals_ip_final_shj_ajm",
}

UNMAPPED_CODE = "unmapped_columns"
OPTIONAL_CODE = "optional_columns"
AMBIGUOUS_CODE = "ambiguous_alias"

_notices: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "pms_upload_header_notices",
    default=None,
)


def header_identity(value: Any) -> str:
    """Compare headers after case and whitespace differences only."""
    return "".join(char for char in str(value).casefold() if not char.isspace())


def _loose(value: Any) -> str:
    """Header identity without underscores and dots (the pharmacy and sales match rule)."""
    return header_identity(value).replace("_", "").replace(".", "")


def is_padding_header(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none"}:
        return True
    return header_identity(text).startswith("unnamed:")


def exact_header_text(value: Any) -> str | None:
    if is_padding_header(value):
        return None
    return str(value)


def begin_header_notices() -> Token:
    return _notices.set([])


def reset_header_notices(token: Token) -> None:
    _notices.reset(token)


def publish_header_notices(items: Iterable[Mapping[str, Any]]) -> None:
    bucket = _notices.get()
    if bucket is None:
        return
    bucket.extend(dict(item) for item in items)


def current_header_notices() -> list[dict[str, Any]]:
    bucket = _notices.get()
    return [] if not bucket else [dict(item) for item in bucket]


def collecting_upload_header_notices(method: Callable) -> Callable:
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        token = begin_header_notices()
        try:
            return method(self, *args, **kwargs)
        finally:
            reset_header_notices(token)

    return wrapper


def _configured_names(team_name: str) -> set[str]:
    try:
        config = load_team_config(team_name)
    except ConfigurationError:
        return set()
    names: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).endswith("_col") and isinstance(value, str):
                    text = value.strip()
                    if text and not text.startswith("$"):
                        names.add(header_identity(text))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(config)
    return names


def _declared_reads(sheet_name: str) -> tuple[tuple[str, ...], tuple[tuple[str, int], ...], tuple[str, ...], tuple[str, ...]]:
    """What the team's importer declares it reads: names, positional runs, patterns, exclusions."""
    module_name = _READ_MODULES.get(sheet_name)
    if module_name is None:
        return (), (), (), ()
    module = importlib.import_module(module_name)
    return (
        tuple(getattr(module, "READ_COLUMNS", ())),
        tuple(getattr(module, "READ_ANCHORS", ())),
        tuple(getattr(module, "READ_PATTERNS", ())),
        tuple(getattr(module, "READ_PATTERN_EXCLUDE", ())),
    )


def _known_identities(sheet_name: str) -> set[str]:
    known = {header_identity(name) for name in SHARED_METADATA_COLUMNS}
    if is_outbound_sheet(sheet_name):
        known.update(header_identity(name) for name in ORDINARY_OUTBOUND_HEADERS)
        known.update(header_identity(name) for name in OUTBOUND_ESTABLISHED_COLUMNS)
        known.add(header_identity(QUALITY_TARGET_COLUMN))
        known.update(_configured_names("Outbound"))
    else:
        known.update(header_identity(name) for name in SHARED_READ_COLUMNS)
        known.update(_configured_names(sheet_name))
        names, _anchors, _patterns, _excludes = _declared_reads(sheet_name)
        known.update(header_identity(name) for name in names)
    return known


def _anchor_identities(texts: list[str], anchors: Iterable[tuple[str, int]]) -> set[str]:
    """Positional reads: the importer slices N columns from an anchor, up to the grade column."""
    identities = [header_identity(text) for text in texts]
    grade = header_identity(GRADE_COLUMN)
    read: set[str] = set()
    for anchor, count in anchors:
        anchor_identity = header_identity(anchor)
        if anchor_identity not in identities:
            continue
        start = identities.index(anchor_identity)
        for index in range(start, min(start + count, len(identities))):
            if identities[index] == grade:
                break
            read.add(identities[index])
    return read


def _pattern_identities(texts: list[str], patterns: Iterable[str], excludes: Iterable[str]) -> set[str]:
    """Name-pattern reads (a keyword in the loose name), with the excluded spellings removed."""
    wanted = tuple(patterns)
    if not wanted:
        return set()
    banned = tuple(excludes)
    read: set[str] = set()
    for text in texts:
        loose = _loose(text)
        if any(pattern in loose for pattern in wanted) and not any(item in loose for item in banned):
            read.add(header_identity(text))
    return read


def _is_layout(identity: str, row_identities: set[str]) -> bool:
    if identity in {header_identity(name) for name in LAYOUT_COLUMNS}:
        return True
    if _LAYOUT_TITLE.match(identity):
        return True
    match = _DUPLICATE_SUFFIX.match(identity)
    return bool(match and match.group("base") in row_identities)


def _collect(columns: Iterable[Any], accepted) -> tuple[list[str], bool]:
    found: list[str] = []
    seen: set[str] = set()
    for column in columns:
        text = exact_header_text(column)
        if text is None:
            continue
        identity = header_identity(text)
        if identity in seen or not accepted(identity):
            continue
        seen.add(identity)
        found.append(text)
    truncated = len(found) > MAX_HEADERS_PER_NOTICE
    return found[:MAX_HEADERS_PER_NOTICE], truncated


def _notice(sheet_name: str, code: str, headers: list[str], truncated: bool) -> dict[str, Any]:
    return {
        "sheet": str(sheet_name),
        "code": code,
        "headers": list(headers),
        "truncated": bool(truncated),
    }


def classify_raw_headers(sheet_name: str, columns: Iterable[Any]) -> list[dict[str, Any]]:
    """Classify a header row that has not been cropped or renamed."""
    column_list = list(columns)
    optional_ids = _optional_identities(sheet_name)
    known_ids = _known_identities(sheet_name) - optional_ids
    texts = [text for text in (exact_header_text(column) for column in column_list) if text is not None]
    row_ids = {header_identity(text) for text in texts}
    layout_ids: set[str] | None = None
    if not is_outbound_sheet(sheet_name):
        _names, anchors, patterns, excludes = _declared_reads(sheet_name)
        known_ids |= _anchor_identities(texts, anchors)
        known_ids |= _pattern_identities(texts, patterns, excludes)
        layout_ids = row_ids
    optional_headers, optional_truncated = _collect(
        column_list,
        lambda identity: identity in optional_ids,
    )

    def unmapped(identity: str) -> bool:
        if identity in known_ids or identity in optional_ids:
            return False
        if layout_ids is not None and _is_layout(identity, layout_ids):
            return False
        return True

    unmapped_headers, unmapped_truncated = _collect(column_list, unmapped)
    notices = []
    if unmapped_headers:
        notices.append(_notice(sheet_name, UNMAPPED_CODE, unmapped_headers, unmapped_truncated))
    if optional_headers:
        notices.append(_notice(sheet_name, OPTIONAL_CODE, optional_headers, optional_truncated))
    return notices


def _optional_identities(sheet_name: str) -> set[str]:
    if not is_outbound_sheet(sheet_name):
        return set()
    return {
        header_identity(name)
        for name in (*PRODUCTIVITY_ACTUAL_ALIASES, *PRODUCTIVITY_TARGET_ALIASES)
    }


def bound_column_warnings(warnings: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    bounded = []
    source = [dict(item) for item in warnings if isinstance(item, Mapping)]
    for warning in source[:MAX_NOTICES]:
        headers = [
            str(header)
            for header in list(warning.get("headers") or [])
            if isinstance(header, str) and header.strip()
        ]
        item = {
            "sheet": str(warning.get("sheet") or "Sheet"),
            "code": str(warning.get("code") or UNMAPPED_CODE),
            "headers": headers[:MAX_HEADERS_PER_NOTICE],
            "truncated": bool(warning.get("truncated") or len(headers) > MAX_HEADERS_PER_NOTICE),
        }
        if item["headers"]:
            bounded.append(item)
    if len(source) > MAX_NOTICES and bounded:
        bounded[-1]["truncated"] = True
    return bounded


def ambiguous_target_message(warnings: Iterable[Mapping[str, Any]]) -> str:
    names: list[str] = []
    sheet = "Outbound"
    for warning in warnings:
        sheet = str(warning.get("sheet") or sheet)
        for header in warning.get("headers") or []:
            text = str(header)
            if text not in names:
                names.append(text)
    shown = " and ".join(f"'{name}'" for name in names[:4]) or "the quality target columns"
    return (
        f"{sheet} columns {shown} both contain values that do not match. "
        "Neither value was used as the quality target."
    )


def _cell_ratio(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    converted = convert_percentage(value)
    try:
        number = float(converted)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _same_ratio(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)


def _matching_positions(frame: pd.DataFrame, identity: str) -> list[int]:
    return [
        position
        for position, column in enumerate(frame.columns)
        if header_identity(column) == identity
    ]


def _original_names(source_headers: Iterable[Any], identity: str, fallback: str) -> list[str]:
    names: list[str] = []
    for column in source_headers:
        text = exact_header_text(column)
        if text is None or header_identity(text) != identity or text in names:
            continue
        names.append(text)
    return names or [fallback]


def apply_outbound_quality_target_alias(
    frame: pd.DataFrame,
    source_headers: Iterable[Any],
    sheet_name: str,
) -> list[dict[str, Any]]:
    """Copy T.Quality Target onto T.Quality% when that configured column is empty.

    The original alias column stays on the frame. Two populated values that do
    not normalize to the same ratio are reported and neither value is written
    over the other. Only these two quality-target columns are read.
    """
    if frame is None or not is_outbound_sheet(sheet_name):
        return []
    alias_identity = header_identity(QUALITY_TARGET_ALIAS)
    canonical_identity = header_identity(QUALITY_TARGET_COLUMN)
    alias_positions = _matching_positions(frame, alias_identity)
    canonical_positions = _matching_positions(frame, canonical_identity)
    if not alias_positions:
        return []

    alias_names = _original_names(source_headers, alias_identity, QUALITY_TARGET_ALIAS)
    canonical_names = (
        _original_names(source_headers, canonical_identity, QUALITY_TARGET_COLUMN)
        if canonical_positions
        else []
    )
    conflict = len(alias_positions) > 1 or len(canonical_positions) > 1
    alias_series = frame.iloc[:, alias_positions[0]]
    canonical_series = frame.iloc[:, canonical_positions[0]] if canonical_positions else None
    alias_ratios: list[float | None] = []
    canonical_ratios: list[float | None] = []
    for index in range(len(frame.index)):
        alias_ratio = _cell_ratio(alias_series.iloc[index])
        canonical_ratio = None if canonical_series is None else _cell_ratio(canonical_series.iloc[index])
        if (
            alias_ratio is not None
            and canonical_ratio is not None
            and not _same_ratio(alias_ratio, canonical_ratio)
        ):
            conflict = True
        alias_ratios.append(alias_ratio)
        canonical_ratios.append(canonical_ratio)

    if conflict:
        headers: list[str] = []
        for name in (*canonical_names, *alias_names):
            if name not in headers:
                headers.append(name)
        notice = _notice(sheet_name, AMBIGUOUS_CODE, headers, False)
        _remember(frame, [notice])
        return [notice]

    if not any(ratio is not None for ratio in alias_ratios):
        return []
    if canonical_series is None:
        frame[QUALITY_TARGET_COLUMN] = [
            ratio if ratio is not None else pd.NA for ratio in alias_ratios
        ]
        return []

    updated = canonical_series.copy()
    changed = False
    for index, (alias_ratio, canonical_ratio) in enumerate(zip(alias_ratios, canonical_ratios)):
        if canonical_ratio is None and alias_ratio is not None:
            updated.iloc[index] = alias_ratio
            changed = True
    if changed:
        frame.iloc[:, canonical_positions[0]] = updated
    return []


def attach_header_notices(frame: pd.DataFrame, sheet_name: str, source_headers: Iterable[Any]) -> list[dict[str, Any]]:
    header_list = list(source_headers)
    notices = classify_raw_headers(sheet_name, header_list)
    _remember(frame, notices)
    frame.attrs["source_header_names"] = [
        text for column in header_list if (text := exact_header_text(column)) is not None
    ]
    return notices


def _remember(frame: pd.DataFrame, notices: list[dict[str, Any]]) -> None:
    current = [dict(item) for item in list(frame.attrs.get("column_warnings") or [])]
    frame.attrs["column_warnings"] = current + [dict(item) for item in notices]
    publish_header_notices(notices)
