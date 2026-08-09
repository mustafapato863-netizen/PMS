from __future__ import annotations

from sqlalchemy.orm import Session

from models.models import KPIValue, PerformanceRecord, Team


class KPIConfigurationRepository:
    """Read persisted KPI targets without loading employee performance rows."""

    def __init__(self, db: Session):
        self.db = db

    def list_distinct_employee_targets(self) -> list[tuple[str, str, str, int, str, float]]:
        rows = (
            self.db.query(
                Team.id,
                Team.name,
                Team.display_name,
                PerformanceRecord.position_name,
                PerformanceRecord.year,
                PerformanceRecord.month,
                KPIValue.kpi_key,
                KPIValue.target_value,
            )
            .join(
                PerformanceRecord,
                (KPIValue.record_id == PerformanceRecord.id)
                & (KPIValue.record_year == PerformanceRecord.year),
            )
            .join(Team, PerformanceRecord.team_id == Team.id)
            .filter(
                Team.team_level == "employee",
                PerformanceRecord.performance_level == "Employee",
            )
            .distinct()
            .all()
        )
        return [
            (
                str(display_name or team_name).strip(),
                str(position_name or ""),
                str(kpi_key),
                int(year),
                str(month),
                float(target_value),
            )
            for _team_id, team_name, display_name, position_name, year, month, kpi_key, target_value in rows
        ]
