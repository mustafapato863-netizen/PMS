from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
import uuid
import logging

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from models.models import ManagementKPIConfig, ManagementKPIConfigHistory, ManagementKPISnapshot, Team
from services.balanced_scorecard_service import BalancedScorecardService, MONTHS
from utils.team_identity import (
    create_management_team_identity,
    get_scoped_team,
    logical_team_name,
)

logger = logging.getLogger(__name__)


class ManagementBSCSchemaError(RuntimeError):
    """Raised when the database is missing required management BSC schema."""


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _period_value(month: str, year: int) -> tuple[int, int]:
    return (int(year), MONTHS.get(str(month), 0))


def _direction_ratio(direction: str, actual_value: float | None, target_value: float | None) -> float | None:
    if actual_value is None or target_value is None:
        return None
    if direction == "lower_better":
        if actual_value == 0:
            return 1.0 if target_value == 0 else None
        return target_value / actual_value
    if target_value == 0:
        return 1.0 if actual_value == 0 else None
    return actual_value / target_value


def _highest_position(positions: set[str]) -> str | None:
    def rank(position: str) -> tuple[int, str]:
        value = position.lower()
        # ponytail: title-based ranking; replace with position_rank if hierarchy becomes configurable.
        score = next((score for title, score in (
            ("chief", 6), ("vice president", 5), ("president", 6), ("director", 4),
            ("head", 3), ("group manager", 3), ("general manager", 3), ("manager", 2),
        ) if title in value), 0)
        if "assistant" in value or "account manager" in value:
            score -= 1
        return score, value

    return max(positions, key=rank) if positions else None


class ManagementBSCService:
    def __init__(self, db: Session):
        self.db = db

    def import_template_rows(
        self,
        *,
        rows: list[dict[str, Any]],
        updated_by: str | None = None,
        default_team_name: str | None = None,
        source_filename: str | None = None,
    ) -> dict[str, Any]:
        try:
            upload_batch_id = uuid.uuid4()
            grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                team_name = str(row.get("team") or default_team_name or "").strip()
                if not team_name:
                    raise ValueError("Template row is missing Team")
                grouped_rows[team_name].append(row)

            total_config_rows = 0
            total_snapshot_rows = 0
            touched_period_labels: set[str] = set()
            touched_levels: set[str] = set()

            for team_name, team_rows in grouped_rows.items():
                team = self._get_or_create_team(team_name)
                payload = self._build_database_payload(team_rows)
                touched_periods = sorted({(row["performance_level"], row["effective_year"], row["effective_month"]) for row in payload["config_rows"]})

                for level, year, month in touched_periods:
                    self._replace_period_config(
                        team_id=team.id,
                        performance_level=level,
                        year=year,
                        month=month,
                        config_rows=[row for row in payload["config_rows"] if row["performance_level"] == level and row["effective_year"] == year and row["effective_month"] == month],
                        updated_by=updated_by,
                        upload_batch_id=upload_batch_id,
                        source_filename=source_filename,
                    )
                    self._replace_period_snapshots(
                        team_id=team.id,
                        performance_level=level,
                        year=year,
                        month=month,
                        snapshot_rows=[row for row in payload["snapshots"] if row["performance_level"] == level and row["year"] == year and row["month"] == month],
                        updated_by=updated_by,
                        upload_batch_id=upload_batch_id,
                    )
                    touched_period_labels.add(f"{month} {year}")
                    touched_levels.add(level)

                total_config_rows += len(payload["config_rows"])
                total_snapshot_rows += len(payload["snapshots"])

            self.db.commit()

            return {
                "upload_batch_id": str(upload_batch_id),
                "teams": sorted(grouped_rows),
                "rows_count": len(rows),
                "config_rows": total_config_rows,
                "snapshot_rows": total_snapshot_rows,
                "periods": sorted(touched_period_labels),
                "levels": sorted(touched_levels),
                "data_source": "database_config",
            }
        except Exception as exc:
            self.db.rollback()
            if isinstance(exc, SQLAlchemyError):
                self._raise_if_schema_mismatch(exc, operation="import management BSC template")
            raise

    def build_scorecard_dataset(
        self,
        *,
        team_name: str,
        performance_level: str,
        month: str,
        year: int | None,
        employee_ids: list[str] | None,
        history_months: int,
        selected_kpi: str | None,
        base_config: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            team = get_scoped_team(self.db, team_name, "management")
            if not team:
                return self._empty_response(
                    team_name,
                    performance_level,
                    month,
                    year,
                    history_months,
                )
            snapshots = (
                self.db.query(ManagementKPISnapshot)
                .filter(
                    ManagementKPISnapshot.team_id == team.id,
                    ManagementKPISnapshot.performance_level == performance_level,
                )
                .all()
            )
        except SQLAlchemyError as exc:
            self._raise_if_schema_mismatch(exc, operation="read management BSC scorecard")
            raise
        top_position = _highest_position({row.position_name for row in snapshots if row.position_name})
        if employee_ids:
            selected_ids = set(employee_ids)
            snapshots = [row for row in snapshots if row.employee_identifier in selected_ids]

        if not snapshots:
            return self._empty_response(
                team_name, performance_level, month, year, history_months,
                top_position=top_position, team_id=str(team.id),
            )

        periods = sorted({_period_value(row.month, row.year) for row in snapshots if MONTHS.get(row.month)})
        if not periods:
            return self._empty_response(
                team_name, performance_level, month, year, history_months,
                top_position=top_position, team_id=str(team.id),
            )

        candidates = [period for period in periods if year is None or period[0] == year]
        if month and month != "All":
            candidates = [period for period in candidates if period[1] == MONTHS.get(month, 0)]
        if not candidates:
            return self._empty_response(
                team_name, performance_level, month, year, history_months,
                top_position=top_position, available_periods=periods, team_id=str(team.id),
            )
        selected_period = candidates[-1]

        active_periods = [period for period in periods if period <= selected_period]
        active_periods = active_periods[-max(1, min(history_months, 24)):]
        allowed_periods = set(active_periods)

        snapshots = [row for row in snapshots if _period_value(row.month, row.year) in allowed_periods]
        try:
            configs = (
                self.db.query(ManagementKPIConfig)
                .filter(
                    ManagementKPIConfig.team_id == team.id,
                    ManagementKPIConfig.performance_level == performance_level,
                    ManagementKPIConfig.is_active.is_(True),
                )
                .all()
            )
        except SQLAlchemyError as exc:
            self._raise_if_schema_mismatch(exc, operation="read management BSC config")
            raise
        configs = [row for row in configs if _period_value(row.effective_month, row.effective_year) in allowed_periods]
        if not configs:
            return self._empty_response(
                team_name, performance_level, month, year, history_months,
                top_position=top_position, available_periods=periods, team_id=str(team.id),
            )

        config_lookup = self._group_configs(configs)
        records = self._build_records_from_snapshots(snapshots, config_lookup)
        if not records:
            return self._empty_response(
                team_name, performance_level, month, year, history_months,
                top_position=top_position, available_periods=periods, team_id=str(team.id),
            )

        period_configs = {
            period: self._build_runtime_config(configs, base_config, team_name, performance_level, period)
            for period in active_periods
        }
        config = period_configs[selected_period]
        data = BalancedScorecardService.build(
            records=records,
            config=config,
            team=team_name,
            performance_level=performance_level,
            month=month,
            year=selected_period[0],
            employee_ids=employee_ids,
            history_months=history_months,
            selected_kpi=selected_kpi,
            period_configs=period_configs,
        )
        data.setdefault("selection", {})
        data.setdefault("team", {}).update({
            "id": str(team.id),
            "name": logical_team_name(team),
            "team_level": "management",
            "top_position": top_position,
        })
        data["available_periods"] = [
            {
                "month": next(name for name, number in MONTHS.items() if number == period[1]),
                "year": period[0],
            }
            for period in periods
        ]
        data["selection"]["data_source"] = "database_config"
        data["selection"]["effective_month"] = next((name for name, number in MONTHS.items() if number == selected_period[1]), None)
        data["selection"]["effective_year"] = selected_period[0]
        data["selection"]["config_scope_summary"] = {
            "position_configs": len([row for row in configs if row.position_name]),
            "employee_overrides": len([row for row in configs if row.employee_identifier]),
        }
        return data

    def list_configs(self, *, team_name: str, performance_level: str | None = None) -> list[dict[str, Any]]:
        try:
            team = get_scoped_team(self.db, team_name, "management")
            if not team:
                return []
            query = self.db.query(ManagementKPIConfig).filter(ManagementKPIConfig.team_id == team.id)
            if performance_level:
                query = query.filter(ManagementKPIConfig.performance_level == performance_level)
            rows = query.order_by(
                ManagementKPIConfig.effective_year.desc(),
                ManagementKPIConfig.effective_month.desc(),
                ManagementKPIConfig.display_order.asc(),
            ).all()
        except SQLAlchemyError as exc:
            self._raise_if_schema_mismatch(exc, operation="list management KPI config")
            raise
        return [
            {
                "id": str(row.id),
                "performance_level": row.performance_level,
                "position_name": row.position_name,
                "employee_identifier": row.employee_identifier,
                "perspective_key": row.perspective_key,
                "kpi_key": row.kpi_key,
                "kpi_label": row.kpi_label,
                "direction": row.direction,
                "weight": _to_float(row.weight),
                "target_value": _to_float(row.target_value),
                "target_unit": row.target_unit,
                "effective_month": row.effective_month,
                "effective_year": row.effective_year,
                "display_order": row.display_order,
                "updated_by": row.updated_by,
            }
            for row in rows
        ]

    def list_history(self, *, team_name: str) -> list[dict[str, Any]]:
        try:
            team = get_scoped_team(self.db, team_name, "management")
            if not team:
                return []
            rows = (
                self.db.query(ManagementKPIConfigHistory)
                .filter(ManagementKPIConfigHistory.team_id == team.id)
                .order_by(ManagementKPIConfigHistory.changed_at.desc())
                .all()
            )
        except SQLAlchemyError as exc:
            self._raise_if_schema_mismatch(exc, operation="list management KPI history")
            raise
        return [
            {
                "id": str(row.id),
                "config_id": str(row.config_id) if row.config_id else None,
                "action": row.action,
                "old_values": row.old_values,
                "new_values": row.new_values,
                "changed_at": row.changed_at.isoformat() if row.changed_at else None,
                "changed_by": row.changed_by,
            }
            for row in rows
        ]

    def list_management_teams(self) -> list[str]:
        try:
            rows = (
                self.db.query(Team.display_name, Team.name)
                .join(ManagementKPIConfig, ManagementKPIConfig.team_id == Team.id)
                .filter(
                    ManagementKPIConfig.is_active.is_(True),
                    Team.team_level == "management",
                )
                .distinct()
                .order_by(Team.display_name.asc(), Team.name.asc())
                .all()
            )
        except SQLAlchemyError as exc:
            self._raise_if_schema_mismatch(exc, operation="list management KPI teams")
            raise
        return sorted({display_name or name for display_name, name in rows if display_name or name})

    def list_management_team_scopes(self) -> list[dict[str, str]]:
        try:
            rows = (
                self.db.query(Team)
                .join(ManagementKPIConfig, ManagementKPIConfig.team_id == Team.id)
                .filter(
                    ManagementKPIConfig.is_active.is_(True),
                    Team.team_level == "management",
                    Team.is_active.is_(True),
                )
                .distinct()
                .order_by(Team.display_name.asc(), Team.name.asc())
                .all()
            )
        except SQLAlchemyError as exc:
            self._raise_if_schema_mismatch(exc, operation="list management team scopes")
            raise
        return [
            {
                "id": str(team.id),
                "name": logical_team_name(team),
                "team_level": "management",
            }
            for team in rows
        ]

    def list_analysis_records(self) -> list[dict[str, Any]]:
        """Return management snapshots in the canonical scorecard record shape.

        This is intentionally read-only and reuses the same snapshot/config resolution
        used by ``build_scorecard_dataset`` so reporting and insights do not invent a
        second management scoring path.
        """
        try:
            teams = (
                self.db.query(Team)
                .filter(Team.team_level == "management", Team.is_active.is_(True))
                .all()
            )
            snapshots = self.db.query(ManagementKPISnapshot).all()
            configs = self.db.query(ManagementKPIConfig).filter(ManagementKPIConfig.is_active.is_(True)).all()
        except SQLAlchemyError as exc:
            self._raise_if_schema_mismatch(exc, operation="read management analysis records")
            raise

        team_by_id = {team.id: team for team in teams}
        snapshots_by_scope: dict[tuple[Any, str], list[ManagementKPISnapshot]] = defaultdict(list)
        configs_by_scope: dict[tuple[Any, str], list[ManagementKPIConfig]] = defaultdict(list)
        for row in snapshots:
            if row.team_id in team_by_id:
                snapshots_by_scope[(row.team_id, row.performance_level)].append(row)
        for row in configs:
            if row.team_id in team_by_id:
                configs_by_scope[(row.team_id, row.performance_level)].append(row)

        result: list[dict[str, Any]] = []
        for scope_key, scope_snapshots in snapshots_by_scope.items():
            scope_configs = configs_by_scope.get(scope_key, [])
            if not scope_configs:
                continue
            team = team_by_id[scope_key[0]]
            records = self._build_records_from_snapshots(scope_snapshots, self._group_configs(scope_configs))
            for record in records:
                record["team"] = logical_team_name(team)
                record["region"] = team.region
                record["position"] = record.get("raw_data", {}).get("Position")
                measured = [
                    value for value in record["kpi_values"]
                    if value.get("contribution") is not None and value.get("weight_applied")
                ]
                measured_weight = sum(float(value["weight_applied"]) for value in measured)
                contribution = sum(float(value["contribution"]) for value in measured)
                record["evaluation"]["score"] = contribution / measured_weight * 100 if measured_weight else None
                result.append(record)
        return result

    def list_option_rows(self) -> list[dict[str, Any]]:
        """Return configured management dimensions without building scorecards."""
        logical_name = func.coalesce(Team.display_name, Team.name)
        configured_scope = or_(
            and_(
                ManagementKPIConfig.position_name == ManagementKPISnapshot.position_name,
                ManagementKPIConfig.employee_identifier.is_(None),
            ),
            and_(
                ManagementKPIConfig.employee_identifier == ManagementKPISnapshot.employee_identifier,
                ManagementKPIConfig.position_name.is_(None),
            ),
        )
        try:
            rows = (
                self.db.query(
                    ManagementKPISnapshot.employee_identifier,
                    ManagementKPISnapshot.employee_name,
                    logical_name.label("logical_team_name"),
                    ManagementKPISnapshot.month,
                    ManagementKPISnapshot.year,
                    Team.region,
                    ManagementKPISnapshot.performance_level,
                    ManagementKPISnapshot.position_name,
                )
                .join(Team, Team.id == ManagementKPISnapshot.team_id)
                .join(
                    ManagementKPIConfig,
                    and_(
                        ManagementKPIConfig.team_id == ManagementKPISnapshot.team_id,
                        ManagementKPIConfig.performance_level == ManagementKPISnapshot.performance_level,
                        ManagementKPIConfig.effective_month == ManagementKPISnapshot.month,
                        ManagementKPIConfig.effective_year == ManagementKPISnapshot.year,
                        ManagementKPIConfig.is_active.is_(True),
                        configured_scope,
                    ),
                )
                .filter(
                    Team.team_level == "management",
                    Team.is_active.is_(True),
                )
                .distinct()
                .all()
            )
        except SQLAlchemyError as exc:
            self._raise_if_schema_mismatch(exc, operation="read management option rows")
            raise

        return [
            {
                "employee_id": str(employee_id),
                "employee_name": str(employee_name),
                "team": str(team_name),
                "month": str(month),
                "year": int(year),
                "region": str(region) if region else None,
                "performance_level": str(performance_level),
                "position": str(position) if position else None,
                "grade": None,
                "status": None,
            }
            for employee_id, employee_name, team_name, month, year, region, performance_level, position in rows
        ]

    def list_upload_batches(self) -> list[dict[str, Any]]:
        try:
            rows = (
                self.db.query(ManagementKPIConfigHistory, Team.display_name, Team.name)
                .join(Team, Team.id == ManagementKPIConfigHistory.team_id)
                .filter(ManagementKPIConfigHistory.upload_batch_id.isnot(None))
                .order_by(ManagementKPIConfigHistory.changed_at.desc())
                .all()
            )
        except SQLAlchemyError as exc:
            self._raise_if_schema_mismatch(exc, operation="list management upload batches")
            raise
        grouped: dict[str, dict[str, Any]] = {}
        for history, display_name, stored_name in rows:
            team_name = display_name or stored_name
            batch_id = str(history.upload_batch_id)
            item = grouped.setdefault(batch_id, {
                "id": batch_id,
                "filename": history.source_filename or "Management Template",
                "uploaded_at": history.changed_at.isoformat() if history.changed_at else None,
                "uploaded_by": history.changed_by or "Admin",
                "teams": set(),
                "periods": set(),
                "levels": set(),
            })
            item["teams"].add(team_name)
            for row in history.new_values or []:
                if row.get("effective_month") and row.get("effective_year"):
                    item["periods"].add(f"{row['effective_month']} {row['effective_year']}")
                if row.get("performance_level"):
                    item["levels"].add(row["performance_level"])
        return [
            {
                **item,
                "teams": sorted(item["teams"]),
                "periods": sorted(item["periods"]),
                "levels": sorted(item["levels"]),
            }
            for item in grouped.values()
        ]

    def delete_upload_batch(self, batch_id: str) -> dict[str, Any]:
        try:
            batch_uuid = uuid.UUID(str(batch_id))
            config_count = (
                self.db.query(ManagementKPIConfig)
                .filter(ManagementKPIConfig.upload_batch_id == batch_uuid)
                .delete(synchronize_session=False)
            )
            snapshot_count = (
                self.db.query(ManagementKPISnapshot)
                .filter(ManagementKPISnapshot.upload_batch_id == batch_uuid)
                .delete(synchronize_session=False)
            )
            history_count = (
                self.db.query(ManagementKPIConfigHistory)
                .filter(ManagementKPIConfigHistory.upload_batch_id == batch_uuid)
                .delete(synchronize_session=False)
            )
            self.db.commit()
            return {
                "upload_batch_id": batch_id,
                "config_rows_deleted": config_count,
                "snapshot_rows_deleted": snapshot_count,
                "history_rows_deleted": history_count,
            }
        except SQLAlchemyError as exc:
            self.db.rollback()
            self._raise_if_schema_mismatch(exc, operation="delete management upload batch")
            raise

    def _get_team(self, team_name: str) -> Team:
        team = get_scoped_team(self.db, team_name, "management")
        if not team:
            raise ValueError(f"Team '{team_name}' was not found in database")
        return team

    def _get_or_create_team(self, team_name: str) -> Team:
        team = get_scoped_team(self.db, team_name, "management", include_inactive=True)
        if team:
            team.is_active = True
            return team
        employee_team = get_scoped_team(self.db, team_name, "employee", include_inactive=True)
        return create_management_team_identity(
            self.db,
            team_name,
            region=employee_team.region if employee_team else "UAE",
        )

    def _build_database_payload(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        from services.bsc_template_service import bsc_template_service

        return bsc_template_service.build_database_payload(rows)

    def _replace_period_config(
        self,
        *,
        team_id,
        performance_level: str,
        year: int,
        month: str,
        config_rows: list[dict[str, Any]],
        updated_by: str | None,
        upload_batch_id,
        source_filename: str | None,
    ) -> None:
        existing = (
            self.db.query(ManagementKPIConfig)
            .filter(
                ManagementKPIConfig.team_id == team_id,
                ManagementKPIConfig.performance_level == performance_level,
                ManagementKPIConfig.effective_year == year,
                ManagementKPIConfig.effective_month == month,
            )
            .all()
        )
        old_snapshots = [self._serialize_config_row(row) for row in existing]
        if existing:
            for row in existing:
                self.db.delete(row)

        new_configs = []
        for row in config_rows:
            payload = dict(row)
            payload.pop("scope_type", None)
            new_configs.append(ManagementKPIConfig(team_id=team_id, updated_by=updated_by, upload_batch_id=upload_batch_id, **payload))
        if new_configs:
            self.db.add_all(new_configs)

        self.db.add(
            ManagementKPIConfigHistory(
                team_id=team_id,
                action="replace",
                old_values=old_snapshots,
                new_values=config_rows,
                upload_batch_id=upload_batch_id,
                source_filename=source_filename,
                changed_by=updated_by,
            )
        )

    def _replace_period_snapshots(
        self,
        *,
        team_id,
        performance_level: str,
        year: int,
        month: str,
        snapshot_rows: list[dict[str, Any]],
        updated_by: str | None,
        upload_batch_id,
    ) -> None:
        (
            self.db.query(ManagementKPISnapshot)
            .filter(
                ManagementKPISnapshot.team_id == team_id,
                ManagementKPISnapshot.performance_level == performance_level,
                ManagementKPISnapshot.year == year,
                ManagementKPISnapshot.month == month,
            )
            .delete(synchronize_session=False)
        )
        new_snapshots = [
            ManagementKPISnapshot(
                team_id=team_id,
                updated_by=updated_by,
                upload_batch_id=upload_batch_id,
                **{key: value for key, value in row.items() if key != "display_order"}
            )
            for row in snapshot_rows
        ]
        if new_snapshots:
            self.db.add_all(new_snapshots)

    def _group_configs(self, configs: list[ManagementKPIConfig]) -> dict[tuple[int, int], dict[str, dict[str, list[ManagementKPIConfig]]]]:
        lookup: dict[tuple[int, int], dict[str, dict[str, list[ManagementKPIConfig]]]] = {}
        for row in configs:
            period = _period_value(row.effective_month, row.effective_year)
            bucket = lookup.setdefault(period, {"position": defaultdict(list), "employee": defaultdict(list)})
            if row.employee_identifier:
                bucket["employee"][row.employee_identifier].append(row)
            elif row.position_name:
                bucket["position"][row.position_name].append(row)
        for bucket in lookup.values():
            for scope_rows in bucket["position"].values():
                scope_rows.sort(key=lambda item: (item.display_order, item.kpi_label))
            for scope_rows in bucket["employee"].values():
                scope_rows.sort(key=lambda item: (item.display_order, item.kpi_label))
        return lookup

    def _build_records_from_snapshots(
        self,
        snapshots: list[ManagementKPISnapshot],
        config_lookup: dict[tuple[int, int], dict[str, dict[str, list[ManagementKPIConfig]]]],
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str, int], dict[str, Any]] = {}
        snapshot_map: dict[tuple[str, str, int], dict[str, ManagementKPISnapshot]] = defaultdict(dict)
        positions: dict[tuple[str, str, int], str] = {}
        names: dict[tuple[str, str, int], str] = {}

        for row in snapshots:
            key = (row.employee_identifier, row.month, int(row.year))
            snapshot_map[key][row.kpi_key] = row
            positions[key] = row.position_name
            names[key] = row.employee_name

        for key, kpi_rows in snapshot_map.items():
            employee_identifier, month, year = key
            period = _period_value(month, year)
            period_configs = config_lookup.get(period, {})
            position_rows = period_configs.get("position", {}).get(positions[key], [])
            employee_rows = period_configs.get("employee", {}).get(employee_identifier, [])
            config_by_kpi = {row.kpi_key: row for row in position_rows}
            config_by_kpi.update({row.kpi_key: row for row in employee_rows})
            config_rows = sorted(config_by_kpi.values(), key=lambda item: (item.display_order, item.kpi_label))
            if not config_rows:
                continue

            record = grouped.setdefault(
                key,
                {
                    "id": f"{employee_identifier}_{month}_{year}",
                    "employee_id": employee_identifier,
                    "employee_name": names[key],
                    "team": None,
                    "month": month,
                    "year": year,
                    "performance_level": config_rows[0].performance_level,
                    "raw_data": {"Position": positions[key], "Period": f"{month} {year}"},
                    "kpi_values": [],
                    "evaluation": {"score": 0, "grade": "B"},
                },
            )

            for config_row in config_rows:
                snapshot_row = kpi_rows.get(config_row.kpi_key)
                actual_value = _to_float(snapshot_row.actual_value) if snapshot_row else None
                target_value = _to_float(config_row.target_value)
                ratio = _direction_ratio(config_row.direction, actual_value, target_value)
                weight = _to_float(config_row.weight) or 0.0
                record["kpi_values"].append(
                    {
                        "kpi_key": config_row.kpi_key,
                        "label": config_row.kpi_label,
                        "perspective": config_row.perspective_key,
                        "direction": config_row.direction,
                        "unit": config_row.target_unit or "%",
                        "actual_value": actual_value,
                        "target_value": target_value,
                        "achievement_ratio": ratio,
                        "weight_applied": weight,
                        "contribution": weight * ratio if ratio is not None else None,
                    }
                )
        return list(grouped.values())

    def _build_runtime_config(
        self,
        configs: list[ManagementKPIConfig],
        base_config: dict[str, Any],
        team_name: str,
        performance_level: str,
        selected_period: tuple[int, int],
    ) -> dict[str, Any]:
        base_bsc = base_config.get("balanced_scorecard", {}) or {}
        base_perspectives = {
            item.get("key"): item
            for item in base_bsc.get("perspectives", [])
            if item.get("key")
        }

        perspective_order = ["Financial", "Customer", "Internal Process", "Learning & Growth"]
        default_meta = {
            "Financial": {"label": "Financial", "focus": "Business profitability & revenue", "display_order": 1, "icon_key": "wallet"},
            "Customer": {"label": "Customer", "focus": "Stakeholder & patient experience", "display_order": 2, "icon_key": "users"},
            "Internal Process": {"label": "Internal Process", "focus": "Operational accuracy & compliance", "display_order": 3, "icon_key": "settings"},
            "Learning & Growth": {"label": "Learning & Growth", "focus": "Staff capacity & digital transformation", "display_order": 4, "icon_key": "graduation-cap"},
        }
        perspectives = []
        for key in perspective_order:
            meta = dict(default_meta[key])
            meta.update(base_perspectives.get(key, {}))
            meta["key"] = key
            perspectives.append(meta)

        ordered = sorted(
            (row for row in configs if _period_value(row.effective_month, row.effective_year) == selected_period),
            key=lambda row: (row.display_order, row.kpi_label),
        )
        seen = set()
        kpis = []
        for row in ordered:
            if row.kpi_key in seen:
                continue
            seen.add(row.kpi_key)
            kpis.append(
                {
                    "key": row.kpi_key,
                    "label": row.kpi_label,
                    "perspective": row.perspective_key,
                    "weight": _to_float(row.weight) or 0.0,
                    "direction": row.direction,
                    "unit": row.target_unit or "%",
                    "color": None,
                    "rollup": "average",
                }
            )

        return {
            "team": team_name,
            "performance_level": performance_level,
            "grade_thresholds": base_config.get("grade_thresholds", {"A": 90, "B": 80, "C": 70, "D": 60}),
            "balanced_scorecard": {
                "enabled": True,
                "perspectives": perspectives,
                "strategy_map_links": base_bsc.get("strategy_map_links", []),
            },
            "kpis": kpis,
        }

    def _serialize_config_row(self, row: ManagementKPIConfig) -> dict[str, Any]:
        return {
            "performance_level": row.performance_level,
            "position_name": row.position_name,
            "employee_identifier": row.employee_identifier,
            "perspective_key": row.perspective_key,
            "kpi_key": row.kpi_key,
            "kpi_label": row.kpi_label,
            "direction": row.direction,
            "weight": _to_float(row.weight),
            "target_value": _to_float(row.target_value),
            "target_unit": row.target_unit,
            "display_order": row.display_order,
            "effective_month": row.effective_month,
            "effective_year": row.effective_year,
        }

    def _empty_response(
        self,
        team_name: str,
        performance_level: str,
        month: str,
        year: int | None,
        history_months: int,
        *,
        top_position: str | None = None,
        available_periods: list[tuple[int, int]] | None = None,
        team_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "team": {
                "id": team_id,
                "name": team_name,
                "team_level": "management",
                "performance_level": performance_level,
                "balanced_scorecard": True,
                "top_position": top_position,
            },
            "selection": {
                "month": month if month != "All" else None,
                "year": year,
                "employee_ids": [],
                "people_count": 0,
                "history_months": history_months,
                "data_source": "database_config",
                "effective_month": month if month != "All" else None,
                "effective_year": year,
                "config_scope_summary": {"position_configs": 0, "employee_overrides": 0},
            },
            "available_periods": [
                {"month": next(name for name, number in MONTHS.items() if number == period[1]), "year": period[0]}
                for period in (available_periods or [])
            ],
            "available_people": [],
            "scorecard": {
                "score": None,
                "status": "No Data",
                "state": "no_data",
                "configured_weight": 0,
                "measured_weight": 0,
                "coverage": None,
                "weighted_contribution": None,
                "record_count": 0,
                "kpi_count": 0,
            },
            "perspectives": [],
            "kpi_table": [],
            "strategy_map": {"links": []},
            "contributors": [],
            "history": [],
            "selected_kpi": None,
        }

    def _raise_if_schema_mismatch(self, exc: SQLAlchemyError, *, operation: str) -> None:
        text = f"{exc.__class__.__name__}: {exc}"
        markers = (
            "UndefinedColumn",
            "UndefinedTable",
            "does not exist",
            "no such column",
            "no such table",
        )
        if any(marker in text for marker in markers):
            logger.error("Management BSC schema mismatch during %s: %s", operation, exc, exc_info=exc)
            raise ManagementBSCSchemaError(
                "Management Overview database schema is out of date. Run backend migrations."
            ) from exc
