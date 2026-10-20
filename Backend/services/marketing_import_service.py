from __future__ import annotations

import datetime
import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import pandas as pd

from config.loader import (
    ConfigurationError,
    load_team_config,
    resolve_position_config,
)
from data_cleaning.standard_mappings import calculate_grade
from models.schemas import Employee, EvaluationData, PerformanceRecord
from services.scoring.engine import EMPLOYEE_POLICY, achievement as engine_achievement, score as engine_score
from utils.performance_levels import normalize_performance_level
from utils.performance_status import status_for_grade


SHEET_NAME = "Marketing"
REQUIRED_COLUMNS = (
    "Employee ID",
    "Region",
    "Team",
    "Employee Name",
    "Position",
    "Performance Level",
    "Date",
    "Perspective",
    "KPI",
    "Direction",
    "Weight",
    "Target Value",
    "Target Unit",
    "Actual Value",
)
ALLOWED_REGIONS = {"EGY": "EGY", "UAE": "UAE", "OTHER": "Other"}
EMPLOYEE_LEVEL_POSITION_OVERRIDES = {"account manager"}
DERIVED_TOLERANCE = Decimal("0.0005")
# Performance Score differences are reported in score points, not ratio.
SCORE_TOLERANCE_POINTS = Decimal("0.5")
WEIGHT_SUM_TOLERANCE = Decimal("0.005")


class MarketingImportValidationError(ValueError):
    status_code = 422

    def __init__(self, errors: list[dict[str, Any]], report: dict[str, Any]):
        super().__init__("Marketing sheet validation failed")
        self.errors = errors
        self.report = {**report, "validation_errors": errors}


@dataclass
class MarketingImportResult:
    employees: list[Employee]
    records: list[PerformanceRecord]
    report: dict[str, Any]


def _normalized_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _lookup_key(value: Any) -> str:
    return _normalized_text(value).casefold()


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _lookup_key(value)).strip("_") or "kpi"


# kpi_values.kpi_key (and the other KPI key columns it feeds) is VARCHAR(50).
GENERATED_KPI_KEY_MAX_LENGTH = 50


def _generated_kpi_key(position: str, label: str) -> str:
    """Deterministic key for a KPI label the config does not know: the same label always gets the same key.

    A key that would not fit the 50-character KPI key columns keeps a readable prefix and ends with a short
    hash of the full key, so it stays unique and stable.
    """
    key = f"mkt_{_slug(position)}_{_slug(label)}"
    if len(key) <= GENERATED_KPI_KEY_MAX_LENGTH:
        return key
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
    return f"{key[:GENERATED_KPI_KEY_MAX_LENGTH - 9].rstrip('_')}_{digest}"


def _clean_employee_id(value: Any) -> str:
    text = _normalized_text(value)
    for bad_char in ("‏", "‎", "​", "﻿"):
        text = text.replace(bad_char, "")
    if text.endswith(".0"):
        text = text[:-2]
    return text.replace(" ", "").upper()


def _direction(value: Any) -> str:
    normalized = re.sub(r"[^a-z]", "", _normalized_text(value).casefold())
    mapping = {
        "higherbetter": "higher_better",
        "higherisbetter": "higher_better",
        "lowerbetter": "lower_better",
        "lowerisbetter": "lower_better",
    }
    return mapping.get(normalized, "")


def _decimal(value: Any) -> Decimal:
    if value is None or pd.isna(value):
        raise InvalidOperation
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("%", "")
    else:
        text = str(value)
    result = Decimal(text)
    if not result.is_finite():
        raise InvalidOperation
    return result


def _date_value(value: Any) -> datetime.datetime:
    if value is None or pd.isna(value):
        raise ValueError("blank date")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = pd.to_datetime(value, unit="D", origin="1899-12-30", errors="raise")
    else:
        parsed = pd.to_datetime(value, errors="raise")
    return parsed.to_pydatetime() if isinstance(parsed, pd.Timestamp) else parsed


def _derived_ratio(value: Any) -> Decimal | None:
    if value is None or pd.isna(value) or _normalized_text(value) == "":
        return None
    try:
        result = _decimal(value)
    except InvalidOperation:
        return None
    return result / Decimal("100") if abs(result) > Decimal("2") else result


def _is_blank(value: Any) -> bool:
    return value is None or pd.isna(value) or _normalized_text(value) == ""


def _status(grade: str) -> str:
    return status_for_grade(grade)


class MarketingImportService:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or load_team_config("Marketing")

    @staticmethod
    def _error(
        errors: list[dict[str, Any]],
        row: int | None,
        column: str | None,
        code: str,
        message: str,
    ) -> None:
        errors.append(
            {
                "sheet": SHEET_NAME,
                "row": row,
                "column": column,
                "code": code,
                "message": message,
            }
        )

    @staticmethod
    def _issue(row: int | None, column: str | None, code: str, message: str, **details: Any) -> dict[str, Any]:
        return {"sheet": SHEET_NAME, "row": row, "column": column, "code": code, "message": message, **details}

    @staticmethod
    def _warning(
        warnings: list[dict[str, Any]],
        row: int,
        column: str,
        actual: Decimal,
        expected: Decimal,
    ) -> None:
        warnings.append(
            {
                "sheet": SHEET_NAME,
                "row": row,
                "column": column,
                "code": "DERIVED_VALUE_MISMATCH",
                "message": f"{column} differs from the backend calculation",
                "uploaded": float(actual),
                "calculated": float(expected),
            }
        )

    def parse_excel(self, excel_file: pd.ExcelFile) -> MarketingImportResult | None:
        if SHEET_NAME not in excel_file.sheet_names:
            return None
        frame = pd.read_excel(excel_file, sheet_name=SHEET_NAME)
        return self.parse_frame(frame)

    def _effective_level(self, row: pd.Series) -> str:
        position = _lookup_key(row.get("Position"))
        if position in EMPLOYEE_LEVEL_POSITION_OVERRIDES:
            return "Employee"
        return normalize_performance_level(_normalized_text(row.get("Performance Level")))

    @staticmethod
    def _position_kpi_sets(position_config: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
        """Every KPI set the config knows for a position: the default set and each period variant."""
        kpi_sets = [("default", position_config.get("kpis", []))]
        for index, variant in enumerate(position_config.get("period_variants", []), start=1):
            if isinstance(variant, dict):
                kpi_sets.append((str(variant.get("id") or f"variant_{index}"), variant.get("kpis", [])))
        return kpi_sets

    @classmethod
    def _configured_index(cls, position_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Label and alias (any period set) to its configured KPI. The first set that names a label wins."""
        index: dict[str, dict[str, Any]] = {}
        for _, kpis in cls._position_kpi_sets(position_config):
            for definition in kpis:
                for label in (definition["label"], *(definition.get("aliases") or [])):
                    index.setdefault(_lookup_key(label), definition)
        return index

    @classmethod
    def _missing_kpi_labels(cls, position_config: dict[str, Any], present_keys: set[str]) -> list[str]:
        """Labels of the configured set closest to this employee-month's KPIs that the sheet did not provide."""
        best = min(
            (kpis for _, kpis in cls._position_kpi_sets(position_config)),
            key=lambda kpis: (
                sum(definition["key"] not in present_keys for definition in kpis),
                -sum(definition["key"] in present_keys for definition in kpis),
            ),
        )
        return [definition["label"] for definition in best if definition["key"] not in present_keys]

    def _reject(
        self,
        key: tuple,
        rows: list[dict[str, Any]],
        issues: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> None:
        """Reject one employee-month: none of it is stored, and the upload lists its rows and reasons."""
        if len(key) == 2:
            employee_id, year, month = None, None, None
            label = f"Row {key[1]}"
        else:
            employee_id, year, month = key
            label = f"{employee_id} in {month} {year}"
        row_numbers = sorted({issue["row"] for issue in issues} | {item["row"] for item in rows})
        reasons = [
            {"row": issue["row"], "column": issue["column"], "code": issue["code"], "message": issue["message"]}
            for issue in issues
        ]
        rejected.append({
            "employee_id": employee_id,
            "year": year,
            "month": month,
            "rows": row_numbers,
            "reasons": reasons,
        })
        details = "; ".join(f"row {reason['row']} {reason['column']}: {reason['message']}" for reason in reasons)
        warnings.append({
            "sheet": SHEET_NAME,
            "row": row_numbers[0],
            "column": "Employee",
            "code": "EMPLOYEE_MONTH_REJECTED",
            "message": f"{label} was not imported ({details})",
            "employee_id": employee_id,
            "year": year,
            "month": month,
            "rows": row_numbers,
        })

    def parse_frame(self, frame: pd.DataFrame) -> MarketingImportResult:
        total_rows = len(frame.index)
        warnings: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
        base_report = {
            "sheet": SHEET_NAME,
            "total_rows": total_rows,
            "employee_rows": 0,
            "excluded_non_employee_rows": 0,
            "excluded_incomplete_rows": 0,
            "employees": 0,
            "performance_records": 0,
            "months": [],
            "years": [],
            "periods": [],
            "warnings": warnings,
            "rejected_employee_months": rejected,
        }
        if missing_columns:
            # Structural problems fail the whole upload. Row-level problems never do.
            errors: list[dict[str, Any]] = []
            for column in missing_columns:
                self._error(errors, 1, column, "MISSING_COLUMN", f"Required column is missing: {column}")
            raise MarketingImportValidationError(errors, base_report)

        # Row-level problems are kept per employee-month. A problem rejects only that employee-month.
        issues_by_key: dict[tuple, list[dict[str, Any]]] = {}
        valid_rows: list[dict[str, Any]] = []
        employee_rows = 0
        excluded_rows = 0
        incomplete_rows = 0

        for zero_index, row in frame.iterrows():
            row_number = int(zero_index) + 2
            row_errors: list[dict[str, Any]] = []
            try:
                level = self._effective_level(row)
            except ValueError as exc:
                # The level decides whether the row is an employee row at all, so the row stands on its own.
                self._error(row_errors, row_number, "Performance Level", "INVALID_LEVEL", str(exc))
                issues_by_key.setdefault(("row", row_number), []).extend(row_errors)
                continue
            if level != "Employee":
                excluded_rows += 1
                continue
            employee_rows += 1

            employee_id = _clean_employee_id(row.get("Employee ID"))
            employee_name = _normalized_text(row.get("Employee Name"))
            team = _normalized_text(row.get("Team"))
            position = _normalized_text(row.get("Position"))
            region_key = _normalized_text(row.get("Region")).upper()
            region = ALLOWED_REGIONS.get(region_key)
            kpi_label = _normalized_text(row.get("KPI"))

            for column, value in (
                ("Employee ID", employee_id),
                ("Employee Name", employee_name),
                ("Team", team),
                ("Position", position),
                ("KPI", kpi_label),
            ):
                if not value:
                    self._error(row_errors, row_number, column, "REQUIRED_VALUE", f"{column} is required")

            if team.casefold() != "marketing":
                self._error(row_errors, row_number, "Team", "INVALID_TEAM", "Employee rows must belong to Marketing")
            if region is None:
                self._error(
                    row_errors,
                    row_number,
                    "Region",
                    "INVALID_REGION",
                    "Region must be EGY, UAE, or Other",
                )

            try:
                period_date = _date_value(row.get("Date"))
            except (ValueError, TypeError):
                period_date = None
                self._error(row_errors, row_number, "Date", "INVALID_DATE", "Date must be a valid Excel date")
            period_label = (
                f"{period_date.strftime('%B')} {period_date.year}" if period_date is not None else "an unknown month"
            )

            key: tuple = (
                (employee_id, period_date.year, period_date.strftime("%B"))
                if employee_id and period_date is not None
                else ("row", row_number)
            )

            try:
                position_config = resolve_position_config(self.config, "Employee", position)
            except ConfigurationError as exc:
                position_config = None
                self._error(row_errors, row_number, "Position", "UNKNOWN_POSITION", str(exc))

            # The sheet defines the KPI. A configured label keeps its key (aliases included), and an
            # unknown label gets a generated key, so no row is refused for not being in the config.
            kpi_key = None
            configured: dict[str, Any] | None = None
            if position_config and kpi_label:
                configured = self._configured_index(position_config).get(_lookup_key(kpi_label))
                kpi_key = configured["key"] if configured else _generated_kpi_key(
                    position_config["position_name"], kpi_label,
                )

            perspective = _normalized_text(row.get("Perspective"))
            if configured is not None and _lookup_key(perspective) != _lookup_key(configured["perspective"]):
                # Perspective comes from the row. A difference from the config is a warning, not an error.
                warnings.append(self._issue(
                    row_number,
                    "Perspective",
                    "PERSPECTIVE_MISMATCH",
                    f"Perspective {perspective or 'blank'} differs from the configured {configured['perspective']} "
                    f"for {kpi_label}, employee {employee_id} in {period_label}; the row's value is used",
                    employee_id=employee_id,
                ))

            direction_text = _normalized_text(row.get("Direction"))
            uploaded_direction = _direction(direction_text)
            direction_pinned = False
            if uploaded_direction:
                # Direction comes from the row. A difference from the config is a warning, not an error.
                direction = uploaded_direction
                if configured is not None and uploaded_direction != configured["direction"]:
                    direction_pinned = True
                    warnings.append(self._issue(
                        row_number,
                        "Direction",
                        "DIRECTION_MISMATCH",
                        f"Direction {direction_text or 'blank'} differs from the configured "
                        f"{configured['direction'].replace('_', ' ')} for {kpi_label}, employee {employee_id} in {period_label}; "
                        "the row's value is used",
                        employee_id=employee_id,
                    ))
            elif configured is not None:
                direction = configured["direction"]
                warnings.append(self._issue(
                    row_number,
                    "Direction",
                    "DIRECTION_MISMATCH",
                    f"Direction {direction_text or 'blank'} differs from the configured "
                    f"{direction.replace('_', ' ')} for {kpi_label}, employee {employee_id} in {period_label}; "
                    "the configured direction is used",
                    employee_id=employee_id,
                ))
            else:
                direction = ""
                self._error(
                    row_errors,
                    row_number,
                    "Direction",
                    "INVALID_DIRECTION",
                    "Direction must be Higher Better or Lower Better",
                )

            unit = _normalized_text(row.get("Target Unit"))
            if not unit:
                self._error(row_errors, row_number, "Target Unit", "REQUIRED_VALUE", "Target Unit is required")

            try:
                weight = _decimal(row.get("Weight"))
            except (InvalidOperation, ValueError):
                weight = None
                self._error(row_errors, row_number, "Weight", "INVALID_NUMBER", "Weight must be numeric")
            if weight is not None and weight < 0:
                self._error(row_errors, row_number, "Weight", "NEGATIVE_VALUE", "Weight cannot be negative")

            if (
                position_config
                and kpi_label
                and _is_blank(row.get("Target Value"))
                and _is_blank(row.get("Actual Value"))
                and not row_errors
            ):
                warnings.append(
                    {
                        "sheet": SHEET_NAME,
                        "row": row_number,
                        "column": "Target Value/Actual Value",
                        "code": "INCOMPLETE_KPI_ROW",
                        "message": "Target Value and Actual Value are both blank; row was excluded from import",
                    }
                )
                incomplete_rows += 1
                continue

            try:
                actual = _decimal(row.get("Actual Value"))
            except (InvalidOperation, ValueError):
                actual = None
                self._error(
                    row_errors,
                    row_number,
                    "Actual Value",
                    "INVALID_NUMBER",
                    "Actual Value must be numeric",
                )
            try:
                target = _decimal(row.get("Target Value"))
            except (InvalidOperation, ValueError):
                target = None
                self._error(
                    row_errors,
                    row_number,
                    "Target Value",
                    "INVALID_NUMBER",
                    "Target Value must be numeric",
                )
            if actual is not None and actual < 0:
                self._error(row_errors, row_number, "Actual Value", "NEGATIVE_VALUE", "Actual Value cannot be negative")
            if target is not None and target < 0:
                self._error(row_errors, row_number, "Target Value", "NEGATIVE_VALUE", "Target Value cannot be negative")

            if row_errors:
                issues_by_key.setdefault(key, []).extend(row_errors)
                continue

            valid_rows.append(
                {
                    "row": row_number,
                    "key": key,
                    "employee_id": employee_id,
                    "employee_name": employee_name,
                    "position": position_config["position_name"],
                    "region": region,
                    "date": period_date,
                    "year": period_date.year,
                    "month": period_date.strftime("%B"),
                    "kpi_key": kpi_key,
                    # A configured KPI keeps its configured label, so stored history reads the same.
                    "kpi_label": configured["label"] if configured else kpi_label,
                    "direction": direction,
                    "direction_pinned": direction_pinned,
                    "perspective": perspective,
                    "unit": unit,
                    "weight": weight,
                    "actual": actual,
                    "target": target,
                    "uploaded_achievement": _derived_ratio(row.get("Achievement %")),
                    "uploaded_weighted": _derived_ratio(row.get("Weighted Score %")),
                    "uploaded_score": _derived_ratio(row.get("Performance Score")),
                }
            )

        base_report["employee_rows"] = employee_rows
        base_report["excluded_non_employee_rows"] = excluded_rows
        base_report["excluded_incomplete_rows"] = incomplete_rows

        grouped: dict[tuple, list[dict[str, Any]]] = {}
        for item in valid_rows:
            grouped.setdefault(item["key"], []).append(item)

        # The KPIs the sheet gives each position in each month, for the missing-KPI hint: the sheet defines the
        # set, so a short month is compared with its peers in the same month before the configuration.
        peer_labels: dict[tuple, dict[str, str]] = {}
        for item in valid_rows:
            peer_labels.setdefault((item["position"], item["year"], item["month"]), {})[item["kpi_key"]] = item["kpi_label"]

        employees_by_id: dict[str, Employee] = {}
        records: list[PerformanceRecord] = []
        for key in dict.fromkeys([*grouped, *issues_by_key]):
            rows = grouped.get(key, [])
            issues = list(issues_by_key.get(key, []))
            if rows:
                first = rows[0]
                employee_id, year, month = first["employee_id"], first["year"], first["month"]
                period_text = f"{employee_id} in {month} {year}"
                group_columns = {
                    "Employee Name": "employee_name",
                    "Position": "position",
                    "Region": "region",
                }
                for column, field in group_columns.items():
                    if len({row[field] for row in rows}) > 1:
                        issues.append(self._issue(
                            first["row"],
                            column,
                            "INCONSISTENT_GROUP",
                            f"{column} must be consistent for {period_text}",
                        ))

                # The employee-month's own rows are its KPI set. Each KPI key may appear once.
                row_by_key: dict[str, dict[str, Any]] = {}
                for item in rows:
                    if item["kpi_key"] in row_by_key:
                        issues.append(self._issue(
                            item["row"],
                            "KPI",
                            "DUPLICATE_KPI",
                            f"KPI {item['kpi_label']} is duplicated for {period_text}",
                        ))
                        continue
                    row_by_key[item["kpi_key"]] = item

                total_weight = sum((item["weight"] for item in rows), Decimal("0"))
                # A row that failed validation is missing from `rows`, so the weights would be short for a
                # reason already reported. Weight and KPI-set checks run only when every row of the month was read.
                rows_complete = not issues_by_key.get(key)
                if rows_complete and abs(total_weight - Decimal("1")) > WEIGHT_SUM_TOLERANCE:
                    issues.append(self._issue(
                        first["row"],
                        "Weight",
                        "WEIGHT_SUM",
                        f"Weights for {period_text} sum to {float(total_weight):.3f}, not 1",
                    ))
                    if total_weight < 1:
                        peers = peer_labels.get((first["position"], year, month), {})
                        missing = [label for kpi_key, label in peers.items() if kpi_key not in row_by_key]
                        source = f"other {first['position']} rows in {month} {year}"
                        if not missing:
                            position_config = resolve_position_config(self.config, "Employee", first["position"])
                            missing = self._missing_kpi_labels(position_config, set(row_by_key))
                            source = "configured, not in this month's rows"
                        if missing:
                            issues.append(self._issue(
                                first["row"],
                                "KPI",
                                "MISSING_KPI",
                                f"Missing KPIs for {period_text}: {', '.join(missing)} ({source})",
                            ))
            if issues:
                self._reject(key, rows, issues, rejected, warnings)
                continue

            kpi_values: list[dict[str, Any]] = []
            engine_inputs: list[dict[str, Any]] = []
            for item in rows:
                actual = item["actual"]
                target = item["target"]
                weight = item["weight"]
                # The engine applies the existing rules: lower_better with zero actual is full
                # credit, higher_better with zero target is zero, and results are capped to 0..1.
                result = engine_achievement(float(actual), float(target), item["direction"], policy=EMPLOYEE_POLICY)
                effective = Decimal(str(result.value))
                contribution = effective * weight
                engine_inputs.append({"achievement": result.value, "weight": float(weight)})

                uploaded_achievement = item["uploaded_achievement"]
                uploaded_weighted = item["uploaded_weighted"]
                if uploaded_achievement is not None and abs(uploaded_achievement - effective) > DERIVED_TOLERANCE:
                    self._warning(warnings, item["row"], "Achievement %", uploaded_achievement, effective)
                if uploaded_weighted is not None and abs(uploaded_weighted - contribution) > DERIVED_TOLERANCE:
                    self._warning(warnings, item["row"], "Weighted Score %", uploaded_weighted, contribution)

                kpi_entry = {
                    "kpi_key": item["kpi_key"],
                    "label": item["kpi_label"],
                    "perspective": item["perspective"],
                    "direction": item["direction"],
                    "unit": item["unit"],
                    "actual_value": float(actual),
                    "target_value": float(target),
                    "achievement_ratio": float(effective.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
                    "weight_applied": float(weight),
                    "contribution": float(contribution.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
                }
                if item.get("direction_pinned"):
                    kpi_entry["evaluation_pinned"] = True
                kpi_values.append(kpi_entry)

            engine_score_points = engine_score(engine_inputs).score or 0.0
            score = Decimal(str(engine_score_points)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            uploaded_score = next((item["uploaded_score"] for item in rows if item["uploaded_score"] is not None), None)
            if uploaded_score is not None:
                uploaded_points = uploaded_score * Decimal("100")
                if abs(uploaded_points - score) > SCORE_TOLERANCE_POINTS:
                    warnings.append(
                        {
                            "sheet": SHEET_NAME,
                            "row": first["row"],
                            "column": "Performance Score",
                            "code": "DERIVED_VALUE_MISMATCH",
                            "message": (
                                f"Performance Score for {employee_id} {first['employee_name']} in {month} {year} "
                                f"is {float(uploaded_points):.2f} in the sheet and {float(score):.2f} from its KPI rows"
                            ),
                            "employee_id": employee_id,
                            "month": month,
                            "year": year,
                            "uploaded": float(uploaded_points),
                            "calculated": float(score),
                        }
                    )

            grade = calculate_grade(
                float(score),
                self.config.get("grade_thresholds"),
            )
            employee = Employee(
                id=employee_id,
                name=first["employee_name"],
                team="Marketing",
                status="Active",
                region=first["region"],
                performance_level="Employee",
                position=first["position"],
            )
            employees_by_id[employee_id] = employee
            records.append(
                PerformanceRecord(
                    id=f"{employee_id}_{year}_{month}",
                    employee_id=employee_id,
                    employee_name=first["employee_name"],
                    team="Marketing",
                    month=month,
                    year=year,
                    region=first["region"],
                    performance_level="Employee",
                    position=first["position"],
                    status=_status(grade),
                    evaluation=EvaluationData(score=float(score), grade=grade),
                    raw_data={
                        "Date": first["date"].date().isoformat(),
                        "Position": first["position"],
                        "Region": first["region"],
                    },
                    kpi_values=kpi_values,
                )
            )

        month_order = {
            month: index
            for index, month in enumerate(
                (
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December",
                ),
                start=1,
            )
        }
        periods = sorted(
            {(record.year, record.month) for record in records},
            key=lambda period: (period[0], month_order[period[1]]),
        )
        report = {
            **base_report,
            "employees": len(employees_by_id),
            "performance_records": len(records),
            "months": list(dict.fromkeys(month for _, month in periods)),
            "years": sorted({year for year, _ in periods}),
            "periods": [{"year": year, "month": month} for year, month in periods],
        }
        if employee_rows == 0:
            warnings.append(
                {
                    "sheet": SHEET_NAME,
                    "row": None,
                    "column": "Performance Level",
                    "code": "NO_EMPLOYEE_ROWS",
                    "message": "Marketing sheet contains no Employee rows",
                }
            )
        return MarketingImportResult(list(employees_by_id.values()), records, report)
