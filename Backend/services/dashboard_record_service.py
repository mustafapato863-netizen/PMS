from __future__ import annotations

from sqlalchemy.orm import Session

from models.models import PerformanceRecord
from repositories.performance_repository import PerformanceRepository as SQLPerformanceRepository
from utils.team_identity import logical_team_name
from config.loader import (
    GLOBAL_KPI_ACHIEVEMENT_CAP,
    ConfigurationError,
    load_team_config,
    resolve_team_config,
)
from models.schemas import PerformanceRecord as SchemaPerformanceRecord
from pydantic import ValidationError
from services.legacy_kpi_evidence import build_legacy_employee_kpi_values


def _normalise_kpi_values(
    values: list[dict],
    config: dict | None,
    config_by_key: dict[str, dict],
) -> list[dict]:
    """Return KPI evidence on one consistent 0-1 achievement/contribution scale.

    Older rows can contain an achievement ratio above 1 and a contribution above
    the configured KPI weight.  The product-wide contract now caps every KPI,
    including rows written by an older ``uncapped`` configuration, so cards,
    analysis, exports, and score calculations cannot disagree.
    """
    result: list[dict] = []
    for raw_value in values:
        value = dict(raw_value)
        definition = config_by_key.get(str(value.get("kpi_key")))
        def _number(key: str, default: float = 0.0) -> float:
            try:
                number = float(value.get(key, default))
            except (TypeError, ValueError):
                return default
            return number if number == number else default

        weight = _number("weight_applied")
        if weight > 1.0:
            weight /= 100.0
        ratio = _number("achievement_ratio")
        if ratio > 2.0:
            ratio /= 100.0
        ratio = max(ratio, 0.0)
        # Target-ratio KPIs can be reconstructed from their canonical actual
        # and target values, removing ambiguity between legacy `2.27` ratios
        # and `227` percentage values.
        if definition is not None and definition.get("score_formula", "target_ratio") == "target_ratio":
            try:
                actual = float(value.get("actual_value"))
                target = float(value.get("target_value"))
            except (TypeError, ValueError):
                actual = target = 0.0
            if target > 0:
                ratio = (
                    target / actual if definition.get("direction") == "lower_better" and actual > 0
                    else actual / target if definition.get("direction") != "lower_better"
                    else 1.0
                )
                ratio = max(ratio, 0.0)
        ratio = min(ratio, GLOBAL_KPI_ACHIEVEMENT_CAP)

        contribution = _number("contribution")
        if contribution > 1.0:
            contribution /= 100.0
        contribution = max(contribution, 0.0)
        contribution = min(contribution, max(weight, 0.0))

        value["achievement_ratio"] = ratio
        value["weight_applied"] = weight
        value["contribution"] = contribution
        value["cap_achievement"] = True
        result.append(value)
    return result


class DashboardRecordService:
    """Canonical SQL-scoped resolver for dashboard/report performance records."""

    def __init__(
        self,
        db: Session,
        sql_repository_cls=SQLPerformanceRepository,
    ):
        self.db = db
        self.sql_repository_cls = sql_repository_cls

    def list_records(
        self,
        *,
        team: str | None = None,
        month: str | None = None,
        employee_id: str | None = None,
        grade: str | None = None,
        status: str | None = None,
        performance_level: str | None = None,
        year: int | None = None,
        position: str | None = None,
        region: str | None = None,
    ):
        sql_repository = self.sql_repository_cls(self.db, PerformanceRecord)
        records = sql_repository.get_dashboard_records(
            team=team,
            month=month,
            employee_id=employee_id,
            grade=grade,
            status=status,
            performance_level=performance_level,
            year=year,
            position=position,
            region=region,
        )
        
        result = []
        resolved_configs: dict[tuple[str, str, str], dict | None] = {}
        for item in records:
            employee = item.employee
            record_team = getattr(item, "team", None) or employee.team
            team_name = logical_team_name(record_team)

            config = None
            config_by_key = {}
            config_key = (
                team_name,
                str(item.performance_level),
                str(item.position_name or employee.position_name or ""),
            )
            if config_key not in resolved_configs:
                try:
                    resolved_configs[config_key] = resolve_team_config(
                        load_team_config(team_name),
                        config_key[1],
                        config_key[2] or None,
                    )
                except (ConfigurationError, KeyError, TypeError):
                    resolved_configs[config_key] = None
            config = resolved_configs[config_key]
            if config:
                config_by_key = {str(kpi.get("key")): kpi for kpi in config.get("kpis", [])}

            # KPI rows are the canonical persisted scoring breakdown.  They
            # must override any stale/missing copy inside record_payload so
            # every dashboard consumer sees the same weights/contributions.
            kpi_values = [
                {
                    "kpi_key": value.kpi_key,
                    "label": config_by_key.get(value.kpi_key, {}).get("label", value.kpi_key),
                    "perspective": config_by_key.get(value.kpi_key, {}).get("perspective"),
                    "unit": config_by_key.get(value.kpi_key, {}).get("unit", "number"),
                    "color": config_by_key.get(value.kpi_key, {}).get("color", "#3B82F6"),
                    "direction": config_by_key.get(value.kpi_key, {}).get("direction", "higher_better"),
                    "actual_value": float(value.actual_value),
                    "target_value": float(value.target_value),
                    "achievement_ratio": (
                        float(value.achievement_ratio) / 100.0
                        if float(value.achievement_ratio) > 2.0
                        else float(value.achievement_ratio)
                    ),
                    "weight_applied": float(value.weight_applied),
                    "contribution": (
                        float(value.contribution) / 100.0
                        if float(value.contribution) > 1.0
                        else float(value.contribution)
                    ),
                }
                for value in item.kpi_values
            ]
            kpi_values = _normalise_kpi_values(kpi_values, config, config_by_key)

            payload = getattr(item, "record_payload", None)
            if isinstance(payload, dict):
                try:
                    rich_record = SchemaPerformanceRecord.model_validate(payload)
                    persisted_weights = {
                        str(value.kpi_key): float(value.weight_applied)
                        for value in item.kpi_values
                    }
                    repaired_kpis = build_legacy_employee_kpi_values(
                        team_name,
                        rich_record.raw_data,
                        weights=persisted_weights,
                        config=config,
                    )
                    scoped_kpis = (
                        [value for value in kpi_values if value["kpi_key"] in config_by_key]
                        if team_name == "Pre-Approvals IP Elective Dubai" and config_by_key
                        else kpi_values
                    )
                    canonical_kpis = _normalise_kpi_values(
                        repaired_kpis or scoped_kpis or rich_record.kpi_values,
                        config,
                        config_by_key,
                    )
                    reconciled_score = float(item.score)
                    reconciled_grade = item.grade
                    has_measured_contribution = any(
                        float(value.get("contribution", 0.0) or 0.0) > 0
                        for value in canonical_kpis
                    )
                    if canonical_kpis and has_measured_contribution:
                        reconciled_score = round(
                            min(sum(float(value.get("contribution", 0.0)) for value in canonical_kpis), 1.0) * 100.0,
                            2,
                        )
                        thresholds = (config or {}).get("grade_thresholds", {})
                        if reconciled_score >= float(thresholds.get("A", 95)):
                            reconciled_grade = "A"
                        elif reconciled_score >= float(thresholds.get("B", 85)):
                            reconciled_grade = "B"
                        elif reconciled_score >= float(thresholds.get("C", 75)):
                            reconciled_grade = "C"
                        elif reconciled_score >= float(thresholds.get("D", 65)):
                            reconciled_grade = "D"
                        else:
                            reconciled_grade = "E"
                    elif team_name == "Sales" and repaired_kpis:
                        reconciled_score = round(
                            min(sum(float(value["contribution"]) for value in repaired_kpis), 1.0) * 100.0,
                            2,
                        )
                        if reconciled_score >= 95.0:
                            reconciled_grade = "A"
                        elif reconciled_score >= 90.0:
                            reconciled_grade = "B"
                        elif reconciled_score >= 80.0:
                            reconciled_grade = "C"
                        elif reconciled_score >= 70.0:
                            reconciled_grade = "D"
                        else:
                            reconciled_grade = "E"
                    rich_evaluation = rich_record.evaluation.model_copy(
                        update={"score": reconciled_score, "grade": reconciled_grade}
                    )
                    result.append(rich_record.model_copy(update={
                        "id": str(item.id),
                        "employee_id": str(employee.employee_id),
                        "employee_name": str(employee.name),
                        "team": team_name,
                        "month": str(item.month),
                        "year": int(item.year),
                        "region": item.region or employee.region,
                        "performance_level": str(item.performance_level),
                        "position": item.position_name or employee.position_name,
                        "status": item.status,
                        "upload_id": str(item.upload_id) if getattr(item, "upload_id", None) else None,
                        "evaluation": rich_evaluation,
                        "kpi_values": canonical_kpis,
                    }))
                    continue
                except ValidationError:
                    # Older/partial payloads remain readable from relational
                    # columns.  A malformed payload must not hide the record.
                    pass

            fallback_kpis = (
                [value for value in kpi_values if value["kpi_key"] in config_by_key]
                if team_name == "Pre-Approvals IP Elective Dubai" and config_by_key
                else kpi_values
            )
            fallback_kpis = _normalise_kpi_values(fallback_kpis, config, config_by_key)
            fallback_score = float(item.score)
            fallback_grade = item.grade
            if fallback_kpis and any(
                float(value.get("contribution", 0.0) or 0.0) > 0
                for value in fallback_kpis
            ):
                fallback_score = round(min(sum(float(value.get("contribution", 0.0)) for value in fallback_kpis), 1.0) * 100.0, 2)
                thresholds = (config or {}).get("grade_thresholds", {})
                fallback_grade = (
                    "A" if fallback_score >= float(thresholds.get("A", 95)) else
                    "B" if fallback_score >= float(thresholds.get("B", 85)) else
                    "C" if fallback_score >= float(thresholds.get("C", 75)) else
                    "D" if fallback_score >= float(thresholds.get("D", 65)) else
                    "E"
                )

            result.append(SchemaPerformanceRecord(
                id=str(item.id),
                employee_id=str(employee.employee_id),
                employee_name=str(employee.name),
                team=team_name,
                month=str(item.month),
                year=int(item.year),
                region=item.region or employee.region,
                performance_level=str(item.performance_level),
                position=item.position_name or employee.position_name,
                status=item.status,
                evaluation={"score": fallback_score, "grade": fallback_grade},
                raw_data={},
                kpi_values=fallback_kpis,
            ))
            
        return result

    def list_option_rows(self) -> list[dict[str, object]]:
        """Return lightweight dimensions without loading KPI/config payloads."""
        sql_repository = self.sql_repository_cls(self.db, PerformanceRecord)
        return sql_repository.get_option_rows()

    def list_analysis_records(self):
        """Return the same canonical persisted records used by dashboards."""
        return self.list_records()

