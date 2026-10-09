"""Draft, approve, preview, upload pin, apply, and rollback for one exact month."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.models import (
    Action,
    EvaluationRevision,
    EvaluationScope,
    GeneratedReport,
    KPIValue,
    PerformancePlan,
    PerformanceRecord,
    Team,
    TeamConfigurationVersion,
)
from services.evaluation.access import AccessDenied, EvaluationError, TargetConflict, require_action
from services.evaluation.catalog import EvaluationCatalog
from services.evaluation.periods import month_aliases, month_name, month_number, previous_period
from services.evaluation.resolver import (
    approved_version,
    assert_schema,
    basis_payload,
    schema_ready,
    score_basis,
    snapshot_lines,
)
from services.evaluation.scoring import SUPPORTED_DIRECTIONS, decimal_places
from utils.performance_status import status_for_grade
from utils.team_identity import logical_team_name


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _checksum(snapshot: dict) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decimal(value):
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _as_uuid(value, message: str):
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise EvaluationError(message, code="not_found") from exc


def _actor_id(actor: dict):
    raw = (actor or {}).get("user_id")
    if raw is None or raw == "":
        return None
    return _as_uuid(raw, "Authenticated user is unavailable.")


def _copy_lines(lines: list[dict]) -> list[dict]:
    return json.loads(json.dumps(lines))


class EvaluationWorkflow:
    def __init__(self, db: Session):
        self.db = db
        self.catalog = EvaluationCatalog(db)

    def _ready(self) -> None:
        assert_schema(self.db)

    def _scope(self, scope_id) -> EvaluationScope:
        self._ready()
        parsed = _as_uuid(scope_id, "Evaluation scope was not found.")
        scope = self.db.query(EvaluationScope).filter(EvaluationScope.id == parsed).one_or_none()
        if scope is None:
            self.catalog.sync()
            scope = self.db.query(EvaluationScope).filter(EvaluationScope.id == parsed).one_or_none()
        if scope is None:
            raise EvaluationError("Evaluation scope was not found.", code="not_found")
        return scope

    def _team_name(self, scope: EvaluationScope) -> str:
        if scope.team_id:
            team = self.db.query(Team).filter(Team.id == scope.team_id).one_or_none()
            if team is not None:
                return logical_team_name(team)
        return scope.display_name

    def sync_catalog(self, scope: dict) -> dict:
        self._ready()
        rows = self.catalog.sync()
        visible = []
        for row in rows:
            try:
                require_action(scope, self._team_name(row), "applied" if row.readiness != "supported" else "version")
            except AccessDenied:
                if str(scope.get("role") or "") not in {"Admin", "General Manager", "Performance Team"}:
                    continue
                try:
                    require_action(scope, self._team_name(row), "applied")
                except AccessDenied:
                    continue
            visible.append(self.catalog.serialize(row))
        return {
            "scopes": visible,
            "schema_gaps": [
                "KPIValue does not store direction. Pinned direction is kept on the approved version and the record payload.",
                "Older team_configuration_versions rows have no level or position. They are not treated as monthly bindings.",
                "Historical formulas that are not higher-is-better or lower-is-better stay blocked and are not backfilled.",
            ],
        }

    def _guard_supported(self, scope_row: EvaluationScope) -> None:
        if scope_row.readiness != "supported":
            raise EvaluationError(
                scope_row.block_reason or "This scope is blocked and is outside the supported rollout.",
                code="scope_blocked",
                readiness=scope_row.readiness,
                block_reason=scope_row.block_reason,
                ambiguous_kpis=list(scope_row.ambiguous_kpis or []),
            )

    def _validate_lines(self, current: list[dict], proposed: list[dict], *, weight_only: bool = False) -> tuple[list[dict], list[str]]:
        current_by_key = {str(line["kpi_key"]): line for line in current}
        if {str(line.get("kpi_key")) for line in proposed} != set(current_by_key):
            raise EvaluationError("KPI keys cannot be added or removed in this release.", code="unsupported_edit")
        cleaned = []
        notes = []
        total = Decimal("0")
        for raw in proposed:
            key = str(raw.get("kpi_key"))
            previous = current_by_key[key]
            direction = str(raw.get("direction") or "")
            if direction not in SUPPORTED_DIRECTIONS:
                raise EvaluationError(
                    "Direction must be higher-is-better or lower-is-better. Other formulas are not editable in this release.",
                    code="unsupported_direction",
                )
            try:
                weight = _decimal(raw.get("weight"))
            except Exception as exc:
                raise EvaluationError("Weight must be a number.", code="invalid_weight") from exc
            if weight is None or weight < 0 or weight > 1 or decimal_places(weight) > 4:
                raise EvaluationError("Weight must be between 0 and 1 with at most 4 decimal places.", code="invalid_weight")
            if weight == 0:
                notes.append(f"{key} weight is zero and is kept visible.")
            target_mode = str(raw.get("target_mode") or "workbook")
            if target_mode not in {"workbook", "fixed"}:
                raise EvaluationError("Target source must be workbook or fixed.", code="unsupported_target")
            target = raw.get("target")
            if target_mode == "fixed":
                try:
                    parsed = _decimal(target)
                except Exception as exc:
                    raise EvaluationError("Fixed target must be a number.", code="unsupported_target") from exc
                if parsed is None or parsed < 0:
                    raise EvaluationError("A fixed target must be zero or greater.", code="unsupported_target")
                target_value = float(parsed)
            else:
                if target not in (None, "", previous.get("target")) and _decimal(target) != _decimal(previous.get("target")):
                    raise EvaluationError(
                        "A workbook-sourced target cannot be overwritten. Switch that KPI to a fixed target first.",
                        code="unsupported_target",
                    )
                target_value = previous.get("target") if previous.get("target_mode") == "workbook" else None
            if weight_only and (
                direction != previous.get("direction")
                or target_mode != previous.get("target_mode")
                or _decimal(target_value) != _decimal(previous.get("target"))
            ):
                raise EvaluationError("Only the weight can change for this edit.", code="unsupported_edit")
            total += weight
            cleaned.append(
                {
                    "kpi_key": key,
                    "label": previous.get("label") or key,
                    "weight": float(weight),
                    "direction": direction,
                    "target": target_value,
                    "target_mode": target_mode,
                    "unit": previous.get("unit") or "%",
                }
            )
        if abs(total - Decimal("1")) > Decimal("0.0001"):
            raise EvaluationError(
                f"Weights total {float(total):.4f}. Approval requires a total of 1 and does not normalize the values.",
                code="invalid_weight_total",
            )
        return cleaned, notes

    def _version_number(self, team_id) -> int:
        current = (
            self.db.query(TeamConfigurationVersion.version_number)
            .filter(TeamConfigurationVersion.team_id == team_id)
            .order_by(TeamConfigurationVersion.version_number.desc())
            .first()
        )
        return int(current[0] if current else 0) + 1

    def _insert_version(self, scope_row: EvaluationScope, year: int, month: int, lines: list[dict], status: str, notes: str, actor: dict) -> TeamConfigurationVersion:
        if scope_row.team_id is None:
            raise EvaluationError("A file-only baseline has no live team to bind.", code="scope_blocked")
        snapshot = {
            "schema": 1,
            "performance_level": scope_row.performance_level,
            "position_name": scope_row.position_name or "",
            "policy": "employee_ratio",
            "lines": lines,
            "grade_thresholds": self.catalog.thresholds(scope_row),
        }
        user_id = _actor_id(actor)
        row = TeamConfigurationVersion(
            id=uuid.uuid4(),
            team_id=scope_row.team_id,
            version_number=self._version_number(scope_row.team_id),
            status=status,
            effective_month=month_name(month),
            effective_year=int(year),
            config_snapshot=snapshot,
            config_checksum=_checksum(snapshot),
            created_by_user_id=user_id,
            published_by_user_id=user_id if status == "approved" else None,
            published_at=_now() if status == "approved" else None,
            notes=notes,
            effective_from_month=month,
            effective_from_year=int(year),
            effective_until_month=month,
            effective_until_year=int(year),
            performance_level=scope_row.performance_level,
            position_name=scope_row.position_name or "",
        )
        self.db.add(row)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise EvaluationError("A binding for this scope and month is already active.", code="duplicate_binding") from exc
        return row

    def _find_version(self, scope_row: EvaluationScope, year: int, month: int, status: str) -> TeamConfigurationVersion | None:
        return (
            self.db.query(TeamConfigurationVersion)
            .filter(
                TeamConfigurationVersion.team_id == scope_row.team_id,
                TeamConfigurationVersion.performance_level == scope_row.performance_level,
                TeamConfigurationVersion.position_name == (scope_row.position_name or ""),
                TeamConfigurationVersion.effective_from_year == int(year),
                TeamConfigurationVersion.effective_from_month == month,
                TeamConfigurationVersion.status == status,
            )
            .one_or_none()
        )

    def open_draft(self, actor: dict, scope_id, year: int, month, *, copy_previous: bool = False) -> dict:
        scope_row = self._scope(scope_id)
        require_action(actor, self._team_name(scope_row), "draft")
        self._guard_supported(scope_row)
        number = month_number(month)
        existing = self._find_version(scope_row, int(year), number, "draft")
        if existing and not copy_previous:
            return self._serialize_version(existing, scope_row)
        if copy_previous:
            prior_year, prior_month = previous_period(int(year), number)
            source = self._find_version(scope_row, prior_year, prior_month, "approved")
            lines = _copy_lines(snapshot_lines(source)) if source else self.catalog.baseline_lines(scope_row)
            note = "Copied from the approved previous month." if source else "No approved previous month. Draft started from the file baseline."
        else:
            lines = self.catalog.baseline_lines(scope_row)
            note = "Draft started from the file baseline."
        if not lines:
            raise EvaluationError("This scope has no KPI baseline to draft.", code="scope_blocked")
        if existing:
            existing.status = "superseded"
            existing.superseded_at = _now()
            self.db.flush()
        created = self._insert_version(scope_row, int(year), number, lines, "draft", note, actor)
        self.db.commit()
        return self._serialize_version(created, scope_row)

    def edit_draft(self, actor: dict, version_id, lines: list[dict], *, weight_only: bool = False) -> dict:
        self._ready()
        version = self._version(version_id)
        scope_row = self._scope_for_version(version)
        require_action(actor, self._team_name(scope_row), "draft")
        self._guard_supported(scope_row)
        if version.status != "draft":
            raise EvaluationError("Approved settings are immutable. Open a new draft.", code="immutable")
        cleaned, notes = self._validate_lines(snapshot_lines(version), lines, weight_only=weight_only)
        snapshot = dict(version.config_snapshot or {})
        snapshot["lines"] = cleaned
        version.config_snapshot = snapshot
        version.config_checksum = _checksum(snapshot)
        if notes:
            version.notes = (version.notes or "") + " " + " ".join(notes)
        self.db.commit()
        body = self._serialize_version(version, scope_row)
        body["diagnostics"] = notes
        return body

    def approve(self, actor: dict, version_id) -> dict:
        self._ready()
        version = self._version(version_id)
        scope_row = self._scope_for_version(version)
        require_action(actor, self._team_name(scope_row), "approve")
        self._guard_supported(scope_row)
        if version.status != "draft":
            raise EvaluationError("Only a draft can be approved.", code="immutable")
        cleaned, _notes = self._validate_lines(snapshot_lines(version), snapshot_lines(version))
        current = self._find_version(scope_row, version.effective_from_year, version.effective_from_month, "approved")
        if current is not None and current.id != version.id:
            current.status = "superseded"
            current.superseded_at = _now()
            self.db.flush()
        version.status = "approved"
        version.published_at = _now()
        version.published_by_user_id = _actor_id(actor)
        snapshot = dict(version.config_snapshot or {})
        snapshot["lines"] = cleaned
        version.config_snapshot = snapshot
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise EvaluationError("Another approval already published this scope and month.", code="duplicate_binding") from exc
        self.db.commit()
        self._bump("config")
        return self._serialize_version(version, scope_row)

    def preview(self, actor: dict, version_id, rows: list[dict]) -> dict:
        self._ready()
        version = self._version(version_id)
        scope_row = self._scope_for_version(version)
        require_action(actor, self._team_name(scope_row), "preview")
        if version.status not in {"draft", "approved"}:
            raise EvaluationError("Preview needs a draft or approved version.", code="not_found")
        body = score_basis(version, rows)
        body["writes"] = 0
        return body

    def run_preview_job(self, actor: dict, version_id, rows: list[dict]) -> dict:
        """Job entry. The caller's grants are read again here, including after revocation."""
        require_action(actor, self._team_name(self._scope_for_version(self._version(version_id))), "job")
        return self.preview(actor, version_id, rows)

    def export_version(self, actor: dict, version_id) -> dict:
        self._ready()
        version = self._version(version_id)
        scope_row = self._scope_for_version(version)
        require_action(actor, self._team_name(scope_row), "export")
        return self._serialize_version(version, scope_row)

    def get_version(self, actor: dict, version_id) -> dict:
        self._ready()
        version = self._version(version_id)
        scope_row = self._scope_for_version(version)
        require_action(actor, self._team_name(scope_row), "version")
        return self._serialize_version(version, scope_row)

    def period(self, actor: dict, scope_id, year: int, month) -> dict:
        scope_row = self._scope(scope_id)
        require_action(actor, self._team_name(scope_row), "version")
        number = month_number(month)
        rows = (
            self.db.query(TeamConfigurationVersion)
            .filter(
                TeamConfigurationVersion.team_id == scope_row.team_id,
                TeamConfigurationVersion.performance_level == scope_row.performance_level,
                TeamConfigurationVersion.position_name == (scope_row.position_name or ""),
                TeamConfigurationVersion.effective_from_year == int(year),
                TeamConfigurationVersion.effective_from_month == number,
                TeamConfigurationVersion.performance_level.isnot(None),
            )
            .order_by(TeamConfigurationVersion.version_number.asc())
            .all()
        )
        return {
            "scope": self.catalog.serialize(scope_row),
            "year": int(year),
            "month": number,
            "month_name": month_name(number),
            "versions": [self._serialize_version(row, scope_row) for row in rows],
            "stored_score": self._stored_score(scope_row, int(year), number, actor),
            "stored_actuals": self._stored_actuals(scope_row, int(year), number, actor),
        }

    def reads(self, actor: dict, scope_id, year: int, months: list) -> dict:
        scope_row = self._scope(scope_id)
        role = str(actor.get("role") or "")
        action = "version" if role in {"Admin", "General Manager", "Performance Team"} else "applied"
        require_action(actor, self._team_name(scope_row), action)
        bodies = []
        for month in months:
            number = month_number(month)
            version = self._find_version(scope_row, int(year), number, "approved")
            bodies.append(
                {
                    "year": int(year),
                    "month": number,
                    "month_name": month_name(number),
                    "version_id": str(version.id) if version else None,
                    "lines": snapshot_lines(version),
                    "stored_score": self._stored_score(scope_row, int(year), number, actor),
                    "pinned": version is not None,
                }
            )
        return {"scope_id": str(scope_row.id), "periods": bodies}

    def apply(self, actor: dict, scope_id, year: int, month) -> dict:
        scope_row = self._scope(scope_id)
        require_action(actor, self._team_name(scope_row), "apply")
        self._guard_supported(scope_row)
        number = month_number(month)
        version = self._find_version(scope_row, int(year), number, "approved")
        if version is None:
            raise EvaluationError("Approve this month before applying it.", code="not_approved")
        records = self._records(scope_row, int(year), number, actor)
        if not records:
            raise EvaluationError(
                "This period has no stored results to recalculate. Apply is blocked until evidence exists.",
                code="insufficient_data",
            )
        prior = self._snapshot(records)
        applied_rows = []
        for record in records:
            rows = [
                {
                    "kpi_key": value.kpi_key,
                    "actual": value.actual_value,
                    "workbook_target": value.target_value,
                    "precomputed_achievement": value.achievement_ratio,
                }
                for value in record.kpi_values
            ]
            if not rows:
                raise EvaluationError(
                    "Stored results have no KPI actuals. Apply is blocked.",
                    code="insufficient_data",
                )
            scored = score_basis(version, rows, check_conflicts=False)
            by_key = {row["kpi_key"]: row for row in scored["rows"]}
            for value in record.kpi_values:
                item = by_key.get(value.kpi_key)
                if item is None:
                    continue
                value.target_value = item["target"] if item["target"] is not None else value.target_value
                value.achievement_ratio = item["achievement"] if item["achievement"] is not None else 0
                value.weight_applied = item["weight"]
                value.contribution = item["contribution"] if item["contribution"] is not None else 0
            record.score = scored["score"] if scored["score"] is not None else record.score
            record.grade = scored["grade"] or record.grade
            record.status = status_for_grade(record.grade)
            payload = dict(record.record_payload or {})
            basis = basis_payload(version)
            payload["evaluation_basis"] = basis
            evaluation = dict(payload.get("evaluation") or {})
            evaluation["score"] = float(record.score)
            evaluation["grade"] = record.grade
            payload["evaluation"] = evaluation
            record.record_payload = payload
            applied_rows.append({"id": str(record.id), "score": float(record.score), "grade": record.grade})
        previous = (
            self.db.query(EvaluationRevision)
            .filter(
                EvaluationRevision.team_id == scope_row.team_id,
                EvaluationRevision.performance_level == scope_row.performance_level,
                EvaluationRevision.position_name == (scope_row.position_name or ""),
                EvaluationRevision.year == int(year),
                EvaluationRevision.month == number,
                EvaluationRevision.status == "active",
            )
            .one_or_none()
        )
        if previous is not None:
            previous.status = "rolled_back"
        revision = EvaluationRevision(
            team_id=scope_row.team_id,
            performance_level=scope_row.performance_level,
            position_name=scope_row.position_name or "",
            year=int(year),
            month=number,
            version_id=version.id,
            status="active",
            previous_revision_id=previous.id if previous else None,
            prior_snapshot=prior,
            applied_snapshot={"records": applied_rows},
            created_by_user_id=_actor_id(actor),
        )
        self.db.add(revision)
        self.db.commit()
        self._bump("data")
        return {"revision_id": str(revision.id), "version_id": str(version.id), "records": applied_rows}

    def rollback(self, actor: dict, revision_id) -> dict:
        self._ready()
        parsed = _as_uuid(revision_id, "Revision was not found.")
        revision = self.db.query(EvaluationRevision).filter(EvaluationRevision.id == parsed).one_or_none()
        if revision is None:
            raise EvaluationError("Revision was not found.", code="not_found")
        team = self.db.query(Team).filter(Team.id == revision.team_id).one()
        require_action(actor, logical_team_name(team), "rollback")
        if revision.status != "active":
            raise EvaluationError("Only the active revision can be rolled back.", code="immutable")
        self._restore(revision.prior_snapshot)
        revision.status = "rolled_back"
        previous = None
        if revision.previous_revision_id:
            previous = self.db.query(EvaluationRevision).filter(EvaluationRevision.id == revision.previous_revision_id).one_or_none()
            if previous is not None:
                previous.status = "active"
        self.db.commit()
        self._bump("data")
        return {"revision_id": str(revision.id), "restored_revision_id": str(previous.id) if previous else None}

    def rescore_uploaded(self, record: PerformanceRecord, team: Team, values: list[KPIValue], start: int) -> None:
        """Pin an approved basis onto rows the upload is about to save. No basis leaves the rows unchanged."""
        if not schema_ready(self.db):
            return
        version = approved_version(
            self.db,
            team_id=team.id,
            level=record.performance_level,
            position=record.position_name,
            year=record.year,
            month=record.month,
        )
        if version is None:
            return
        fresh = values[start:]
        if not fresh:
            return
        rows = [
            {
                "kpi_key": value.kpi_key,
                "actual": value.actual_value,
                "workbook_target": value.target_value,
                "precomputed_achievement": value.achievement_ratio,
            }
            for value in fresh
        ]
        scored = score_basis(version, rows)
        by_key = {item["kpi_key"]: item for item in scored["rows"]}
        for value in fresh:
            item = by_key.get(value.kpi_key)
            if item is None:
                continue
            value.target_value = item["target"] if item["target"] is not None else value.target_value
            value.achievement_ratio = item["achievement"] if item["achievement"] is not None else 0
            value.weight_applied = item["weight"]
            value.contribution = item["contribution"] if item["contribution"] is not None else 0
        payload = dict(record.record_payload or {})
        payload["evaluation_basis"] = scored["basis"]
        record.record_payload = payload

    def protected_texts(self) -> dict:
        """Plans, actions, and saved report bytes. Apply must not change these."""
        return {
            "actions": [(str(row.id), row.action_text, row.status) for row in self.db.query(Action).all()],
            "plans": [(str(row.id), row.name, row.status, str(row.target_value)) for row in self.db.query(PerformancePlan).all()],
            "reports": [(str(row.id), bytes(row.file_data), row.status) for row in self.db.query(GeneratedReport).all()],
        }

    def _records(self, scope_row: EvaluationScope, year: int, month: int, actor: dict) -> list[PerformanceRecord]:
        aliases = {item.casefold() for item in month_aliases(month)}
        query = self.db.query(PerformanceRecord).filter(
            PerformanceRecord.team_id == scope_row.team_id,
            PerformanceRecord.performance_level == scope_row.performance_level,
            PerformanceRecord.year == year,
        )
        rows = [row for row in query.all() if str(row.month).strip().casefold() in aliases]
        position = scope_row.position_name or ""
        rows = [row for row in rows if (row.position_name or "") == position]
        role = str(actor.get("role") or "")
        if role == "Branch Director":
            allowed = {str(value).casefold() for value in actor.get("accessible_branches") or []}
            rows = [row for row in rows if str(row.branch_key or "").casefold() in allowed]
        if role == "Regional Manager":
            allowed = {str(value).casefold() for value in actor.get("accessible_regions") or []}
            rows = [row for row in rows if str(row.region or "").casefold() in allowed]
        if role in {"Employee", "Agent", "Executive"}:
            employee_id = str(actor.get("employee_id") or "")
            rows = [row for row in rows if str(getattr(row.employee, "employee_id", "") or "") == employee_id]
        return rows

    def _stored_score(self, scope_row: EvaluationScope, year: int, month: int, actor: dict):
        rows = self._records(scope_row, year, month, actor)
        if not rows:
            return None
        return float(rows[0].score)

    def _stored_actuals(self, scope_row: EvaluationScope, year: int, month: int, actor: dict) -> dict:
        """Actuals from the same first stored record as the displayed score."""
        rows = self._records(scope_row, year, month, actor)
        if not rows:
            return {}
        actuals = {}
        for value in rows[0].kpi_values:
            if value.actual_value is None:
                continue
            actuals[value.kpi_key] = float(value.actual_value)
        return actuals

    def _snapshot(self, records: list[PerformanceRecord]) -> dict:
        body = []
        for record in records:
            body.append(
                {
                    "id": str(record.id),
                    "year": record.year,
                    "score": str(record.score),
                    "grade": record.grade,
                    "status": record.status,
                    "payload": record.record_payload,
                    "kpis": [
                        {
                            "id": str(value.id),
                            "kpi_key": value.kpi_key,
                            "actual": str(value.actual_value),
                            "target": str(value.target_value),
                            "achievement": str(value.achievement_ratio),
                            "weight": str(value.weight_applied),
                            "contribution": str(value.contribution),
                        }
                        for value in record.kpi_values
                    ],
                }
            )
        return {"records": body}

    def _restore(self, snapshot: dict) -> None:
        for item in snapshot.get("records") or []:
            record = (
                self.db.query(PerformanceRecord)
                .filter(PerformanceRecord.id == uuid.UUID(item["id"]), PerformanceRecord.year == item["year"])
                .one_or_none()
            )
            if record is None:
                continue
            record.score = Decimal(item["score"])
            record.grade = item["grade"]
            record.status = item["status"]
            record.record_payload = item.get("payload")
            by_id = {kpi["id"]: kpi for kpi in item.get("kpis") or []}
            for value in record.kpi_values:
                saved = by_id.get(str(value.id))
                if not saved:
                    continue
                value.actual_value = Decimal(saved["actual"])
                value.target_value = Decimal(saved["target"])
                value.achievement_ratio = Decimal(saved["achievement"])
                value.weight_applied = Decimal(saved["weight"])
                value.contribution = Decimal(saved["contribution"])

    def _version(self, version_id) -> TeamConfigurationVersion:
        self._ready()
        try:
            parsed = uuid.UUID(str(version_id))
        except ValueError as exc:
            raise EvaluationError("Version was not found.", code="not_found") from exc
        version = self.db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == parsed).one_or_none()
        if version is None or version.performance_level is None:
            raise EvaluationError("Version was not found.", code="not_found")
        return version

    def _scope_for_version(self, version: TeamConfigurationVersion) -> EvaluationScope:
        self.catalog.sync()
        team = self.db.query(Team).filter(Team.id == version.team_id).one()
        key = logical_team_name(team).casefold()
        scope = (
            self.db.query(EvaluationScope)
            .filter(
                EvaluationScope.team_key == key,
                EvaluationScope.performance_level == version.performance_level,
                EvaluationScope.position_name == (version.position_name or ""),
            )
            .one_or_none()
        )
        if scope is None:
            raise EvaluationError("Evaluation scope was not found.", code="not_found")
        return scope

    def _serialize_version(self, version: TeamConfigurationVersion, scope_row: EvaluationScope) -> dict:
        return {
            "id": str(version.id),
            "scope_id": str(scope_row.id),
            "status": version.status,
            "version_number": version.version_number,
            "year": version.effective_from_year,
            "month": version.effective_from_month,
            "month_name": month_name(version.effective_from_month),
            "lines": snapshot_lines(version),
            "notes": version.notes,
            "checksum": version.config_checksum,
        }

    def _bump(self, kind: str) -> None:
        try:
            from services.cache_invalidation_service import CacheInvalidationService

            if kind == "data":
                CacheInvalidationService.bump_data_version()
            else:
                CacheInvalidationService.bump_config_version()
        except Exception:
            return
