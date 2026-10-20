"""Employee and Managerial template rows become one department dashboard.

Every person in the department, including supervisors, is stored at performance
level Employee. The spreadsheet level stays on the payload as
``source_performance_level``. KPI display fields are pinned so the dashboard
shows the position's own labels, weights, and directions.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from models.models import Employee, KPIValue, PerformanceRecord, Team
from services.management_template_repair import normalize_rate_measurement
from services.scoring.engine import EMPLOYEE_POLICY, achievement as engine_achievement
from utils.performance_status import status_for_grade
from utils.scoring_rules import letter_grade
from utils.team_identity import get_scoped_team

DEPARTMENT_LEVELS = frozenset({"Employee", "Managerial"})
KPI_KEY_MAX_LENGTH = 50

REGION_BY_TEAM = {
    "finance": "All",
    "human resources": "EGY",
    "it": "EGY",
    "offshore admin & management": "EGY",
    "call center": "EGY",
    "marketing": "EGY",
    "pharmacy": "UAE",
    "rcm": "All",
}

PERSPECTIVE_COLORS = {
    "Financial": "#10B981",
    "Customer": "#3B82F6",
    "Internal Process": "#F59E0B",
    "Learning & Growth": "#8B5CF6",
}


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")
    return cleaned or "kpi"


def _kpi_key(position: str, label: str) -> str:
    key = f"pos_{_slug(position)}_{_slug(label)}"
    if len(key) <= KPI_KEY_MAX_LENGTH:
        return key
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
    return f"{key[: KPI_KEY_MAX_LENGTH - 9].rstrip('_')}_{digest}"


def _quantize(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _stored_direction(direction: str | None) -> str:
    text = (direction or "").casefold()
    if "lower" in text:
        return "lower_better"
    return "higher_better"


def _region_for(team_name: str) -> str:
    return REGION_BY_TEAM.get(team_name.casefold(), "EGY")


class PositionDepartmentImportService:
    def __init__(self, db: Session):
        self.db = db

    def import_parsed_rows(self, rows: list[dict], *, commit: bool = True) -> dict:
        grouped: dict[tuple, list[dict]] = {}
        for row in rows:
            if row.get("performance_level") not in DEPARTMENT_LEVELS:
                continue
            key = (
                str(row.get("team") or "").strip(),
                str(row.get("month") or "").strip(),
                int(row["year"]),
                str(row.get("employee_id") or "").strip(),
                str(row.get("employee_name") or "").strip(),
                str(row.get("position") or "").strip(),
            )
            if not key[0] or not key[1] or not key[3] or not key[5]:
                continue
            grouped.setdefault(key, []).append(row)

        teams: set[str] = set()
        record_count = 0
        for key, group in grouped.items():
            self._upsert_group(key, group)
            teams.add(key[0])
            record_count += 1

        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return {"records": record_count, "teams": sorted(teams)}

    def _employee_team(self, team_name: str) -> Team:
        existing = get_scoped_team(self.db, team_name, "employee", include_inactive=True)
        if existing:
            existing.is_active = True
            if not existing.region:
                existing.region = _region_for(team_name)
            return existing
        team = Team(
            id=uuid.uuid4(),
            name=team_name,
            db_name=team_name,
            display_name=team_name,
            region=_region_for(team_name),
            team_level="employee",
            is_active=True,
        )
        self.db.add(team)
        self.db.flush()
        return team

    def _employee(self, team: Team, code: str, name: str, position: str) -> Employee:
        employee = self.db.query(Employee).filter(Employee.employee_id == code).one_or_none()
        if employee is None:
            employee = Employee(
                id=uuid.uuid4(),
                employee_id=code,
                name=name,
                team_id=team.id,
                region=team.region,
                performance_level="Employee",
                position_name=position,
                is_active=True,
            )
            self.db.add(employee)
            self.db.flush()
            return employee
        employee.name = name
        employee.team_id = team.id
        employee.region = team.region
        employee.performance_level = "Employee"
        employee.position_name = position
        employee.is_active = True
        return employee

    def _upsert_group(self, key: tuple, group: list[dict]) -> None:
        team_name, month, year, code, name, position = key
        source_level = str(group[0].get("performance_level") or "Employee")
        team = self._employee_team(team_name)
        employee = self._employee(team, code, name, position)
        kpi_rows = self._kpi_rows(position, group)
        total = sum((row["contribution"] for row in kpi_rows), Decimal("0"))
        score = (total * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        grade = letter_grade(float(score))
        status = status_for_grade(grade)
        payload_kpis = [
            {
                "kpi_key": row["kpi_key"],
                "label": row["label"],
                "perspective": row["perspective"],
                "unit": row["unit"],
                "direction": row["direction"],
                "color": row["color"],
                "actual_value": float(row["actual_value"]),
                "target_value": float(row["target_value"]),
                "achievement_ratio": float(row["achievement_ratio"]),
                "weight_applied": float(row["weight_applied"]),
                "contribution": float(row["contribution"]),
                "evaluation_pinned": True,
            }
            for row in kpi_rows
        ]
        payload = {
            "id": f"{code}_{year}_{month}",
            "employee_id": code,
            "employee_name": name,
            "team": team_name,
            "month": month,
            "year": year,
            "region": team.region,
            "performance_level": "Employee",
            "position": position,
            "role": position,
            "status": status,
            "source_performance_level": source_level,
            "evaluation": {"score": float(score), "grade": grade},
            "raw_data": {"Position": position, "Period": f"{month} {year}"},
            "kpi_values": payload_kpis,
        }
        record = (
            self.db.query(PerformanceRecord)
            .filter(
                PerformanceRecord.employee_id == employee.id,
                PerformanceRecord.month == month,
                PerformanceRecord.year == year,
            )
            .one_or_none()
        )
        if record is None:
            record = PerformanceRecord(
                id=uuid.uuid4(),
                year=year,
                employee_id=employee.id,
                team_id=team.id,
                month=month,
                performance_level="Employee",
                position_name=position,
                region=team.region,
                score=score,
                grade=grade,
                status=status,
                record_payload=payload,
            )
            self.db.add(record)
            self.db.flush()
        else:
            record.team_id = team.id
            record.performance_level = "Employee"
            record.position_name = position
            record.region = team.region
            record.score = score
            record.grade = grade
            record.status = status
            record.record_payload = payload
            self.db.query(KPIValue).filter(KPIValue.record_id == record.id).delete(synchronize_session=False)
            self.db.flush()

        self.db.add_all([
            KPIValue(
                id=uuid.uuid4(),
                record_id=record.id,
                record_year=record.year,
                kpi_key=row["kpi_key"],
                actual_value=row["actual_value"],
                target_value=row["target_value"],
                achievement_ratio=row["achievement_ratio"],
                weight_applied=row["weight_applied"],
                contribution=row["contribution"],
            )
            for row in kpi_rows
        ])

    def _kpi_rows(self, position: str, group: list[dict]) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()
        for item in group:
            label = str(item.get("kpi_label") or "").strip()
            key = _kpi_key(position, label)
            if key in seen:
                continue
            seen.add(key)
            actual = item.get("actual_value")
            target = item.get("target_value")
            raw_unit = item.get("target_unit")
            raw_direction = item.get("direction")
            unit, direction, actual_raw, target_raw = normalize_rate_measurement(
                label,
                "" if raw_unit is None else str(raw_unit),
                None if raw_direction is None else str(raw_direction),
                None if actual is None else float(actual),
                None if target is None else float(target),
            )
            actual_number = 0.0 if actual_raw is None else float(actual_raw)
            target_number = 0.0 if target_raw is None else float(target_raw)
            direction = _stored_direction(direction)
            result = engine_achievement(actual_number, target_number, direction, policy=EMPLOYEE_POLICY)
            achievement = 0.0 if result.value is None else float(result.value)
            weight = _quantize(float(item.get("weight") or 0))
            achievement_ratio = _quantize(achievement)
            contribution = (achievement_ratio * weight).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            perspective = str(item.get("perspective") or "Internal Process").strip()
            if perspective.casefold() in {"", "none", "null", "nan"}:
                perspective = "Internal Process"
            rows.append({
                "kpi_key": key,
                "label": label,
                "perspective": perspective,
                "unit": unit or "%",
                "direction": direction,
                "color": PERSPECTIVE_COLORS.get(perspective, "#3B82F6"),
                "actual_value": _quantize(actual_number),
                "target_value": _quantize(target_number),
                "achievement_ratio": achievement_ratio,
                "weight_applied": weight,
                "contribution": contribution,
            })
        return rows
