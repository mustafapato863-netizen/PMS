from __future__ import annotations
from utils.scoring_rules import letter_grade

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
from services.legacy_kpi_evidence import build_legacy_employee_kpi_values, normalized_text_memo
from services.outbound_period_basis import normalized_name_memo
from services.preapprovals_offshore_scoring import NEW_METHOD_ID as NEW_OFFSHORE_METHOD_ID
from utils.performance_status import reconciled_status
from utils.kpi_direction import (
    find_kpi_definition,
    flipped_contribution_fix,
    resolve_kpi_direction,
)


def _pinned_basis(item) -> dict | None:
    payload = getattr(item, "record_payload", None)
    if not isinstance(payload, dict):
        return None
    basis = payload.get("evaluation_basis")
    if isinstance(basis, dict) and basis.get("pinned"):
        return basis
    return None


def _pinned_schema_record(item, employee, team_name: str, basis: dict, item_kpi_values=None):
    """Keep the stored payload and overlay identity, stored score, and pinned KPIs.

    The current team file is not consulted. A later configuration change cannot
    recalculate this row.
    """
    payload = item.record_payload if isinstance(item.record_payload, dict) else {}
    try:
        record = SchemaPerformanceRecord.model_validate(payload)
    except ValidationError:
        record = SchemaPerformanceRecord(
            id=str(item.id),
            employee_id=str(employee.employee_id),
            employee_name=str(employee.name),
            team=team_name,
            month=str(item.month),
            year=int(item.year),
            evaluation={"score": float(item.score), "grade": item.grade},
            raw_data=payload.get("raw_data") if isinstance(payload.get("raw_data"), dict) else {},
        )
    lines = {str(line.get("kpi_key")): line for line in basis.get("lines") or []}
    stored_kpis = {str(value.get("kpi_key")): value for value in (record.kpi_values or []) if isinstance(value, dict)}
    kpi_values = []
    for value in (item.kpi_values if item_kpi_values is None else item_kpi_values):
        line = lines.get(str(value.kpi_key), {})
        stored = stored_kpis.get(str(value.kpi_key), {})
        kpi_values.append(
            {
                "kpi_key": value.kpi_key,
                "label": line.get("label") or stored.get("label") or value.kpi_key,
                "direction": line.get("direction") if line.get("direction") is not None else stored.get("direction"),
                "evaluation_pinned": True,
                "perspective": stored.get("perspective"),
                "color": stored.get("color"),
                "actual_value": float(value.actual_value),
                "target_value": float(value.target_value),
                "achievement_ratio": float(value.achievement_ratio),
                "weight_applied": float(value.weight_applied),
                "contribution": float(value.contribution),
                "unit": line.get("unit") or stored.get("unit") or "%",
            }
        )
    payload_upload = payload.get("upload_id")
    sql_upload = getattr(item, "upload_id", None)
    return record.model_copy(update={
        "id": str(item.id),
        "employee_id": str(employee.employee_id),
        "employee_name": str(employee.name),
        "team": team_name,
        "month": str(item.month),
        "year": int(item.year),
        "region": item.region or employee.region,
        "branch_key": getattr(item, "branch_key", None),
        "performance_level": str(item.performance_level),
        "position": item.position_name or employee.position_name,
        "status": item.status,
        "upload_id": str(payload_upload) if payload_upload else (str(sql_upload) if sql_upload else None),
        "evaluation": record.evaluation.model_copy(update={"score": float(item.score), "grade": item.grade}),
        "kpi_values": kpi_values,
    })


def _operational_outbound_evidence(team: str | None, values: list) -> bool:
    """Ordinary Outbound evidence caps the final total, not each KPI.

    The legacy builder marks that evidence with ``cap_achievement`` false.
    A positive Productivity weight is the reference contract and stays capped.
    """
    if team != "Outbound":
        return False
    marked = False
    for raw in values:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("kpi_key") or "") == "Productivity":
            try:
                weight = float(raw.get("weight_applied") or 0)
            except (TypeError, ValueError):
                weight = 0.0
            if weight > 1.0:
                weight /= 100.0
            if weight > 0:
                return False
        if raw.get("cap_achievement") is False:
            marked = True
    return marked


def _float_or(value: dict, key: str, default: float = 0.0) -> float:
    try:
        number = float(value.get(key, default))
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def _definition(memo: dict, config: dict | None, value: dict) -> dict | None:
    """find_kpi_definition for a KPI the resolved config does not list, memoised for one resolve call."""
    key = (id(config), value.get("kpi_key"), value.get("label"))
    try:
        return memo[key]
    except KeyError:
        found = memo[key] = find_kpi_definition(config, value.get("kpi_key"), value.get("label"))
        return found
    except TypeError:
        return find_kpi_definition(config, value.get("kpi_key"), value.get("label"))


def _direction(
    memo: dict,
    team: str | None,
    value: dict,
    persisted_direction: str | None,
    definition: dict | None,
) -> tuple[str, str]:
    """resolve_kpi_direction(team, {**value, "direction": persisted_direction}, definition), memoised for one
    resolve call on every input it reads. A default is never memoised, so its warning is logged each time, as before.
    """
    key = (
        team,
        bool(value.get("evaluation_pinned")),
        persisted_direction,
        value.get("kpi_key"),
        value.get("key"),
        value.get("label"),
        (definition or {}).get("direction"),
    )
    try:
        cached = memo.get(key)
    except TypeError:
        return resolve_kpi_direction(team, {**value, "direction": persisted_direction}, definition)
    if cached is not None:
        return cached
    resolved = resolve_kpi_direction(team, {**value, "direction": persisted_direction}, definition)
    if resolved[1] != "default":
        memo[key] = resolved
    return resolved


def _normalise_kpi_values(
    values: list[dict],
    config: dict | None,
    config_by_key: dict[str, dict],
    team: str | None = None,
    persisted_directions: dict[str, str] | None = None,
    memo: dict | None = None,
) -> list[dict]:
    """Return KPI evidence on one consistent achievement/contribution scale.

    Older rows can contain an achievement ratio above 1 and a contribution above
    the configured KPI weight. Teams other than operational Outbound cap every
    KPI, including rows written by an older ``uncapped`` configuration, so cards,
    analysis, exports, and score calculations cannot disagree. Operational
    Outbound keeps an over-target ratio and caps the final total.

    Direction is resolved through ``utils.kpi_direction`` (record config ->
    team config -> persisted -> unambiguous global match -> flagged default)
    and returned with ``direction_source``. A KPI saved under the opposite
    direction (e.g. Marketing ``cw_error_free`` scored lower-is-better before
    the config fix) has its contribution corrected here, so the reconciled
    record score is direction-correct at read time.

    ``memo`` carries the definition and direction lookups of one resolve_records call.
    """
    result: list[dict] = []
    persisted_directions = persisted_directions or {}
    memo = {} if memo is None else memo
    definitions = memo.setdefault("definitions", {})
    directions = memo.setdefault("directions", {})
    operational_outbound = _operational_outbound_evidence(team, values)
    for raw_value in values:
        value = dict(raw_value)
        kpi_key = str(value.get("kpi_key"))
        definition = config_by_key.get(kpi_key) or _definition(definitions, config, value)
        persisted_direction = value.get("direction") or persisted_directions.get(kpi_key)
        direction, direction_source = _direction(directions, team, value, persisted_direction, definition)
        value["direction"] = direction
        value["direction_source"] = direction_source
        weight = _float_or(value, "weight_applied")
        if weight > 1.0:
            weight /= 100.0
        ratio = _float_or(value, "achievement_ratio")
        if ratio > 2.0 and not operational_outbound:
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
                    target / actual if direction == "lower_better" and actual > 0
                    else actual / target if direction != "lower_better"
                    else 1.0
                )
                ratio = max(ratio, 0.0)
        if not operational_outbound:
            ratio = min(ratio, GLOBAL_KPI_ACHIEVEMENT_CAP)

        contribution = _float_or(value, "contribution")
        if contribution > 1.0 and not operational_outbound:
            contribution /= 100.0
        contribution = max(contribution, 0.0)
        if operational_outbound:
            contribution = ratio * weight
        else:
            contribution = min(contribution, max(weight, 0.0))
        if definition is not None and definition.get("score_formula", "target_ratio") == "target_ratio":
            corrected = flipped_contribution_fix(
                value.get("actual_value"),
                value.get("target_value"),
                weight,
                contribution,
                direction,
                persisted_direction,
            )
            if corrected is not None:
                contribution = corrected
                value["direction_corrected"] = True

        value["achievement_ratio"] = ratio
        value["weight_applied"] = weight
        value["contribution"] = contribution
        value["cap_achievement"] = not operational_outbound
        result.append(value)
    return result


def _relational_kpi(value, config_by_key: dict[str, dict]) -> dict:
    """One persisted KPI value row as KPI evidence, before normalisation."""
    definition = config_by_key.get(value.kpi_key, {})
    achievement_ratio = float(value.achievement_ratio)
    contribution = float(value.contribution)
    return {
        "kpi_key": value.kpi_key,
        "label": definition.get("label", value.kpi_key),
        "perspective": definition.get("perspective"),
        "unit": definition.get("unit", "number"),
        "color": definition.get("color", "#3B82F6"),
        # KPIValue has no direction column; the resolver in _normalise_kpi_values decides (never a silent default).
        "direction": None,
        "actual_value": float(value.actual_value),
        "target_value": float(value.target_value),
        "achievement_ratio": achievement_ratio / 100.0 if achievement_ratio > 2.0 else achievement_ratio,
        "weight_applied": float(value.weight_applied),
        "contribution": contribution / 100.0 if contribution > 1.0 else contribution,
    }


def _payload_directions(payload) -> dict[str, str]:
    """``kpi_key -> direction`` as persisted in ``record_payload.kpi_values``."""
    if not isinstance(payload, dict):
        return {}
    directions: dict[str, str] = {}
    for value in payload.get("kpi_values") or []:
        if isinstance(value, dict) and value.get("kpi_key") and value.get("direction"):
            directions[str(value["kpi_key"])] = str(value["direction"])
    return directions


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
        employee_ids: list[str] | None = None,
        grade: str | None = None,
        status: str | None = None,
        performance_level: str | None = None,
        year: int | None = None,
        position: str | None = None,
        region: str | None = None,
        periods: list[tuple[int, str]] | None = None,
        scope: dict | None = None,
        employee_search: str | None = None,
        kpi: str | None = None,
    ):
        sql_repository = self.sql_repository_cls(self.db, PerformanceRecord)
        # The light path reads the same rows without ORM objects; a repository without it keeps the ORM path.
        light_loader = getattr(sql_repository, "get_dashboard_record_rows", None)
        kpi_loader = getattr(sql_repository, "get_kpi_value_rows", None)
        loader = light_loader if callable(light_loader) and callable(kpi_loader) else sql_repository.get_dashboard_records
        records = loader(
            team=team,
            month=month,
            employee_id=employee_id,
            employee_ids=employee_ids,
            grade=grade,
            status=status,
            performance_level=performance_level,
            year=year,
            position=position,
            region=region,
            periods=periods,
            scope=scope,
            employee_search=employee_search,
            kpi=kpi,
        )
        if loader is light_loader:
            return self.resolve_records(records, kpi_rows=kpi_loader([(item.id, item.year) for item in records]))
        return self.resolve_records(records)

    def resolve_records(self, records, kpi_rows: dict[tuple, list] | None = None):
        """``kpi_rows`` holds each record's KPI value rows by (record id, year), read as plain columns by
        list_records. Without it the records' own ``kpi_values`` are read."""
        # The column names of the source rows recur on every record; normalise each once for this call only.
        with normalized_text_memo(), normalized_name_memo():
            return self._resolve_records(records, kpi_rows)

    def _resolve_records(self, records, kpi_rows: dict[tuple, list] | None):
        result = []
        resolved_configs: dict[tuple[str, str, str], dict | None] = {}
        team_configs: dict[str, dict | None] = {}
        # Definition and direction lookups, for this call only.
        memo: dict = {}
        for item in records:
            item_kpi_values = item.kpi_values if kpi_rows is None else kpi_rows.get((item.id, item.year), [])
            employee = item.employee
            record_team = getattr(item, "team", None) or employee.team
            team_name = logical_team_name(record_team)
            pinned_basis = _pinned_basis(item)
            if pinned_basis is not None:
                result.append(_pinned_schema_record(item, employee, team_name, pinned_basis, item_kpi_values))
                continue

            config = None
            config_by_key = {}
            config_key = (
                team_name,
                str(item.performance_level),
                str(item.position_name or employee.position_name or ""),
            )
            if config_key not in resolved_configs:
                team_key = team_name.casefold()
                if team_key not in team_configs:
                    try:
                        team_configs[team_key] = load_team_config(team_name)
                    except (ConfigurationError, KeyError, TypeError):
                        team_configs[team_key] = None
                base_config = team_configs[team_key]
                if base_config is None:
                    resolved_configs[config_key] = None
                else:
                    try:
                        resolved_configs[config_key] = resolve_team_config(
                            base_config,
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
            def relational_kpis() -> list[dict]:
                return [_relational_kpi(value, config_by_key) for value in item_kpi_values]

            payload = getattr(item, "record_payload", None)
            persisted_directions = _payload_directions(payload)
            scoped_cache: list[list[dict]] = []

            def scoped_relational() -> list[dict]:
                # The relational KPI values, normalised once and only when used. Elective Dubai keeps its
                # configured KPIs.
                if not scoped_cache:
                    normalised = _normalise_kpi_values(
                        relational_kpis(), config, config_by_key, team_name, persisted_directions, memo
                    )
                    scoped_cache.append(
                        [value for value in normalised if value["kpi_key"] in config_by_key]
                        if team_name == "Pre-Approvals IP Elective Dubai" and config_by_key
                        else normalised
                    )
                return scoped_cache[0]

            # Keep normalized persisted weights available for both the rich
            # payload and compatibility paths. If the JSON payload is
            # malformed, we can still rebuild canonical KPI evidence from its
            # original source row instead of exposing stale KPIValue actuals.
            persisted_weights = {
                str(value.kpi_key): (
                    float(value.weight_applied) / 100.0
                    if float(value.weight_applied) > 1.0
                    else float(value.weight_applied)
                )
                for value in item_kpi_values
            }
            payload_raw_data: dict = {}
            if isinstance(payload, dict):
                candidate_raw_data = payload.get("raw_data")
                if isinstance(candidate_raw_data, dict):
                    payload_raw_data = candidate_raw_data
            # Rows scored by the June 2026 Offshore method keep their stored KPI
            # values. Rebuilding them with the legacy formula would show the old
            # actuals and targets beside the new score.
            keep_stored_offshore_kpis = (
                team_name == "Pre-Approvals IP Offshore"
                and payload_raw_data.get("ScoringMethod") == NEW_OFFSHORE_METHOD_ID
            )
            if isinstance(payload, dict):
                try:
                    rich_record = SchemaPerformanceRecord.model_validate(payload)
                    repaired_kpis = [] if keep_stored_offshore_kpis else build_legacy_employee_kpi_values(
                        team_name,
                        rich_record.raw_data,
                        weights=persisted_weights,
                        config=config,
                    )
                    canonical_kpis = _normalise_kpi_values(
                        repaired_kpis or scoped_relational() or rich_record.kpi_values,
                        config,
                        config_by_key,
                        team_name,
                        persisted_directions,
                        memo,
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
                        reconciled_grade = letter_grade(reconciled_score)
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
                        "branch_key": getattr(item, "branch_key", None),
                        "performance_level": str(item.performance_level),
                        "position": item.position_name or employee.position_name,
                        # Same grade->status rule as imports, so a record whose
                        # grade was corrected at read time (e.g. cw_error_free
                        # saved lower_better) no longer shows the stale status.
                        "status": reconciled_status(item.status, item.grade, reconciled_grade),
                        "upload_id": str(item.upload_id) if getattr(item, "upload_id", None) else None,
                        "evaluation": rich_evaluation,
                        "kpi_values": canonical_kpis,
                    }))
                    continue
                except ValidationError:
                    # Older/partial payloads remain readable from relational
                    # columns.  A malformed payload must not hide the record.
                    pass

            # Prefer a deterministic rebuild from the original source row for
            # legacy formula-based teams. Older KPIValue rows can contain an
            # achievement copied into actual_value (the source of the 58.7%
            # Initial Error Rate card), while the row counters remain correct.
            repaired_fallback_kpis = [] if keep_stored_offshore_kpis else build_legacy_employee_kpi_values(
                team_name,
                payload_raw_data,
                weights=persisted_weights,
                config=config,
            ) if payload_raw_data else []
            fallback_kpis = repaired_fallback_kpis or scoped_relational()
            fallback_kpis = _normalise_kpi_values(
                fallback_kpis, config, config_by_key, team_name, persisted_directions, memo
            )
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
                branch_key=getattr(item, "branch_key", None),
                performance_level=str(item.performance_level),
                position=item.position_name or employee.position_name,
                status=reconciled_status(item.status, item.grade, fallback_grade),
                evaluation={"score": fallback_score, "grade": fallback_grade},
                raw_data=payload_raw_data,
                kpi_values=fallback_kpis,
            ))
            
        return result

    def list_option_rows(self, scope: dict | None = None, *, include_scores: bool = False) -> list[dict[str, object]]:
        """Return lightweight dimensions without loading KPI/config payloads.

        ``include_scores`` adds the score to the same query (the catalog's period check).
        """
        sql_repository = self.sql_repository_cls(self.db, PerformanceRecord)
        if include_scores:
            return sql_repository.get_option_rows(scope, include_scores=True)
        return sql_repository.get_option_rows(scope)

    def list_kpi_options(self, scope: dict | None = None) -> list[str]:
        """Return authorized KPI keys without materializing dashboard records."""
        sql_repository = self.sql_repository_cls(self.db, PerformanceRecord)
        loader = getattr(sql_repository, "get_option_kpi_keys", None)
        return list(loader(scope)) if callable(loader) else []

    def list_analysis_records(self):
        """Return the same canonical persisted records used by dashboards."""
        return self.list_records()

