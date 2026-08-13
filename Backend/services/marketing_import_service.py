from __future__ import annotations

import datetime
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
from utils.performance_levels import normalize_performance_level


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
WEIGHT_TOLERANCE = Decimal("0.0001")


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


def _clean_employee_id(value: Any) -> str:
    text = _normalized_text(value)
    for bad_char in ("\u200f", "\u200e", "\u200b", "\ufeff"):
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
    if grade == "A":
        return "Exceeds"
    if grade in {"B", "C"}:
        return "Meets"
    return "Below"


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
    def _position_kpi_sets(
        position_config: dict[str, Any],
        period_date: Any | None = None,
    ) -> list[tuple[str, list[dict[str, Any]]]]:
        """Return the default KPI set plus variants effective for a period."""
        kpi_sets = [("default", position_config.get("kpis", []))]
        for index, variant in enumerate(position_config.get("period_variants", []), start=1):
            if not isinstance(variant, dict):
                continue
            if period_date is not None and variant.get("effective_from"):
                try:
                    if pd.Timestamp(variant["effective_from"]).date() > pd.Timestamp(period_date).date():
                        continue
                except (TypeError, ValueError):
                    pass
            kpi_sets.append((str(variant.get("id") or f"variant_{index}"), variant.get("kpis", [])))
        return kpi_sets

    @staticmethod
    def _kpi_lookup(kpis: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            _lookup_key(label): item
            for item in kpis
            for label in (item["label"], *(item.get("aliases") or []))
        }

    @classmethod
    def _select_kpi_set(
        cls,
        position_config: dict[str, Any],
        rows: list[dict[str, Any]],
        period_date: Any | None = None,
    ) -> tuple[str, list[dict[str, Any]], dict[int, dict[str, Any]]]:
        """Select the KPI set whose definitions exactly match one employee period.

        Marketing KPI groupings can change between periods. Matching the complete
        row set keeps legacy periods importable while allowing a new period to
        use a different KPI grouping and weight distribution.
        """
        candidates: list[tuple[int, int, str, list[dict[str, Any]], dict[int, dict[str, Any]]]] = []
        for index, (set_name, kpis) in enumerate(cls._position_kpi_sets(position_config, period_date)):
            lookup = cls._kpi_lookup(kpis)
            matched = {
                item["row"]: lookup.get(_lookup_key(item["kpi_label"]))
                for item in rows
            }
            matched_count = sum(definition is not None for definition in matched.values())
            matched_keys = [definition["key"] for definition in matched.values() if definition is not None]
            expected_keys = {definition["key"] for definition in kpis}
            exact = (
                matched_count == len(rows)
                and len(rows) == len(kpis)
                and len(matched_keys) == len(set(matched_keys))
                and set(matched_keys) == expected_keys
            )
            candidates.append((0 if exact else 1, -matched_count, set_name, kpis, matched))

        candidates.sort(key=lambda candidate: (candidate[0], candidate[1]))
        _, _, set_name, kpis, matched = candidates[0]
        return set_name, kpis, matched

    def parse_frame(self, frame: pd.DataFrame) -> MarketingImportResult:
        total_rows = len(frame.index)
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
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
        }
        for column in missing_columns:
            self._error(errors, 1, column, "MISSING_COLUMN", f"Required column is missing: {column}")
        if errors:
            raise MarketingImportValidationError(errors, base_report)

        valid_rows: list[dict[str, Any]] = []
        employee_rows = 0
        excluded_rows = 0
        incomplete_rows = 0

        for zero_index, row in frame.iterrows():
            row_number = int(zero_index) + 2
            try:
                level = self._effective_level(row)
            except ValueError as exc:
                self._error(errors, row_number, "Performance Level", "INVALID_LEVEL", str(exc))
                continue
            if level != "Employee":
                excluded_rows += 1
                continue
            employee_rows += 1
            row_error_count = len(errors)

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
                    self._error(errors, row_number, column, "REQUIRED_VALUE", f"{column} is required")

            if team.casefold() != "marketing":
                self._error(errors, row_number, "Team", "INVALID_TEAM", "Employee rows must belong to Marketing")
            if region is None:
                self._error(
                    errors,
                    row_number,
                    "Region",
                    "INVALID_REGION",
                    "Region must be EGY, UAE, or Other",
                )

            try:
                period_date = _date_value(row.get("Date"))
            except (ValueError, TypeError):
                period_date = None
                self._error(errors, row_number, "Date", "INVALID_DATE", "Date must be a valid Excel date")

            try:
                position_config = resolve_position_config(self.config, "Employee", position)
            except ConfigurationError as exc:
                position_config = None
                self._error(errors, row_number, "Position", "UNKNOWN_POSITION", str(exc))

            configured_kpis: list[dict[str, Any]] = []
            if position_config:
                configured_kpis = [
                    definition
                    for _, kpis in self._position_kpi_sets(position_config, period_date)
                    for definition in kpis
                    if _lookup_key(kpi_label)
                    in {
                        _lookup_key(label)
                        for label in (definition["label"], *(definition.get("aliases") or []))
                    }
                ]
                if not configured_kpis:
                    self._error(
                        errors,
                        row_number,
                        "KPI",
                        "UNKNOWN_KPI",
                        f"KPI {kpi_label!r} is not configured for {position}",
                    )

            if (
                position_config
                and configured_kpis
                and _is_blank(row.get("Target Value"))
                and _is_blank(row.get("Actual Value"))
                and len(errors) == row_error_count
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
                    errors,
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
                    errors,
                    row_number,
                    "Target Value",
                    "INVALID_NUMBER",
                    "Target Value must be numeric",
                )
            if actual is not None and actual < 0:
                self._error(errors, row_number, "Actual Value", "NEGATIVE_VALUE", "Actual Value cannot be negative")
            if target is not None and target < 0:
                self._error(errors, row_number, "Target Value", "NEGATIVE_VALUE", "Target Value cannot be negative")

            if len(errors) != row_error_count:
                continue

            valid_rows.append(
                {
                    "row": row_number,
                    "employee_id": employee_id,
                    "employee_name": employee_name,
                    "position": position_config["position_name"],
                    "region": region,
                    "date": period_date,
                    "year": period_date.year,
                    "month": period_date.strftime("%B"),
                    "kpi_label": kpi_label,
                    "direction": row.get("Direction"),
                    "perspective": row.get("Perspective"),
                    "target_unit": row.get("Target Unit"),
                    "weight": row.get("Weight"),
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
        if errors:
            raise MarketingImportValidationError(errors, base_report)

        grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
        for item in valid_rows:
            grouped.setdefault((item["employee_id"], item["year"], item["month"]), []).append(item)

        employees_by_id: dict[str, Employee] = {}
        records: list[PerformanceRecord] = []
        for (employee_id, year, month), rows in grouped.items():
            first = rows[0]
            group_columns = {
                "Employee Name": "employee_name",
                "Position": "position",
                "Region": "region",
            }
            for column, key in group_columns.items():
                values = {row[key] for row in rows}
                if len(values) > 1:
                    self._error(
                        errors,
                        first["row"],
                        column,
                        "INCONSISTENT_GROUP",
                        f"{column} must be consistent for {employee_id} in {month} {year}",
                    )

            position_config = resolve_position_config(self.config, "Employee", first["position"])
            _, selected_kpis, matched_kpis = self._select_kpi_set(
                position_config,
                rows,
                first["date"],
            )
            expected_by_key = {item["key"]: item for item in selected_kpis}
            row_by_key: dict[str, dict[str, Any]] = {}
            for item in rows:
                kpi_definition = matched_kpis.get(item["row"])
                if kpi_definition is None:
                    self._error(
                        errors,
                        item["row"],
                        "KPI",
                        "UNKNOWN_KPI",
                        f"KPI {item['kpi_label']!r} is not configured for {first['position']}",
                    )
                    continue

                item["kpi"] = kpi_definition
                uploaded_direction = _direction(item.get("direction"))
                # The Content Writer workbook predates the current scoring rule
                # for error-free content. Keep that legacy label uploadable while
                # using the configured direction as the canonical scoring source.
                legacy_direction = (
                    kpi_definition["key"] == "cw_error_free"
                    and uploaded_direction == "higher_better"
                )
                if uploaded_direction != kpi_definition["direction"] and not legacy_direction:
                    self._error(
                        errors,
                        item["row"],
                        "Direction",
                        "CONFIG_MISMATCH",
                        f"Direction must be {kpi_definition['direction']}",
                    )
                if _lookup_key(item.get("perspective")) != _lookup_key(kpi_definition["perspective"]):
                    self._error(
                        errors,
                        item["row"],
                        "Perspective",
                        "CONFIG_MISMATCH",
                        f"Perspective must be {kpi_definition['perspective']}",
                    )
                if _lookup_key(item.get("target_unit")) != _lookup_key(kpi_definition["unit"]):
                    self._error(
                        errors,
                        item["row"],
                        "Target Unit",
                        "CONFIG_MISMATCH",
                        f"Target Unit must be {kpi_definition['unit']}",
                    )
                try:
                    uploaded_weight = _decimal(item.get("weight"))
                except (InvalidOperation, ValueError):
                    uploaded_weight = None
                    self._error(errors, item["row"], "Weight", "INVALID_NUMBER", "Weight must be numeric")
                if (
                    uploaded_weight is not None
                    and abs(uploaded_weight - Decimal(str(kpi_definition["weight"]))) > WEIGHT_TOLERANCE
                ):
                    self._error(
                        errors,
                        item["row"],
                        "Weight",
                        "CONFIG_MISMATCH",
                        f"Weight must be {kpi_definition['weight']}",
                    )

                kpi_key = kpi_definition["key"]
                if kpi_key in row_by_key:
                    self._error(
                        errors,
                        item["row"],
                        "KPI",
                        "DUPLICATE_KPI",
                        f"KPI {kpi_definition['label']} is duplicated for {employee_id} in {month} {year}",
                    )
                row_by_key[kpi_key] = item

            missing = [item["label"] for key, item in expected_by_key.items() if key not in row_by_key]
            if missing:
                self._error(
                    errors,
                    first["row"],
                    "KPI",
                    "MISSING_KPI",
                    f"Missing KPIs for {employee_id} in {month} {year}: {', '.join(missing)}",
                )
            extra = [key for key in row_by_key if key not in expected_by_key]
            if extra:
                self._error(
                    errors,
                    first["row"],
                    "KPI",
                    "EXTRA_KPI",
                    f"Unexpected KPI keys: {', '.join(extra)}",
                )
            if errors:
                continue

            total_contribution = Decimal("0")
            kpi_values: list[dict[str, Any]] = []
            for kpi_definition in selected_kpis:
                item = row_by_key[kpi_definition["key"]]
                actual = item["actual"]
                target = item["target"]
                if kpi_definition["direction"] == "lower_better":
                    achievement = Decimal("1") if actual == 0 else target / actual
                else:
                    achievement = Decimal("0") if target == 0 else actual / target
                effective = max(Decimal("0"), min(achievement, Decimal("1")))
                weight = Decimal(str(kpi_definition["weight"]))
                contribution = effective * weight
                total_contribution += contribution

                uploaded_achievement = item["uploaded_achievement"]
                uploaded_weighted = item["uploaded_weighted"]
                if (
                    uploaded_achievement is not None
                    and abs(uploaded_achievement - effective) > DERIVED_TOLERANCE
                ):
                    self._warning(
                        warnings,
                        item["row"],
                        "Achievement %",
                        uploaded_achievement,
                        effective,
                    )
                if uploaded_weighted is not None and abs(uploaded_weighted - contribution) > DERIVED_TOLERANCE:
                    self._warning(
                        warnings,
                        item["row"],
                        "Weighted Score %",
                        uploaded_weighted,
                        contribution,
                    )

                kpi_values.append(
                    {
                        "kpi_key": kpi_definition["key"],
                        "label": kpi_definition["label"],
                        "perspective": kpi_definition["perspective"],
                        "direction": kpi_definition["direction"],
                        "unit": kpi_definition["unit"],
                        "actual_value": float(actual),
                        "target_value": float(target),
                        "achievement_ratio": float(achievement.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
                        "weight_applied": float(weight),
                        "contribution": float(contribution.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
                    }
                )

            score = (min(total_contribution, Decimal("1")) * Decimal("100")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            score_ratio = score / Decimal("100")
            for item in rows:
                uploaded_score = item["uploaded_score"]
                if uploaded_score is not None and abs(uploaded_score - score_ratio) > DERIVED_TOLERANCE:
                    self._warning(
                        warnings,
                        item["row"],
                        "Performance Score",
                        uploaded_score,
                        score_ratio,
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

        if errors:
            raise MarketingImportValidationError(errors, base_report)

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
