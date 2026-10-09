"""Draft, approve, preview, upload pin, apply, and rollback for one exact month."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

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
from services.evaluation.access import EvaluationError, TargetConflict, require_action
from services.evaluation.catalog import EvaluationCatalog
from services.evaluation.periods import month_aliases, month_name, month_number, previous_period
from services.evaluation.resolver import (
    approved_version,
    assert_schema,
    basis_payload,
    require_approved_capability,
    schema_ready,
    score_basis,
    snapshot_lines,
)
from services.evaluation.scoring import SUPPORTED_DIRECTIONS, decimal_places
from utils.performance_status import status_for_grade
from utils.report_scope import filter_records_by_scope, filter_records_by_team_levels
from utils.team_identity import logical_team_name


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationConflict(EvaluationError):
    """Stale proof, evidence drift, or a lifecycle collision. Nothing was written."""

    status_code = 409


# Historical re-score reads stored workbook evidence. Other scopes stay blocked
# until their own source audit lands. This is not a weight-only or client bypass.
AUDITED_SCOPE_KEYS = {"coding", "submission"}


def _checksum(snapshot) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_default(value):
    if isinstance(value, Decimal):
        return _canon_decimal(value)
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def _freeze(value):
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default))


def _canon_decimal(value) -> str | None:
    if value is None or value == "":
        return None
    number = Decimal(str(value))
    if not number.is_finite():
        return None
    text_value = format(number, "f")
    if "." in text_value:
        text_value = text_value.rstrip("0").rstrip(".")
    if text_value in {"", "-0"}:
        return "0"
    return text_value


def _iso(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat()
    return str(value)


def _rules_body(snapshot: dict | None) -> dict:
    body = dict(snapshot or {})
    body.pop("preview_evidence", None)
    return body


def _rules_checksum(snapshot: dict | None) -> str:
    return _checksum(_rules_body(snapshot))


def _lineage(snapshot: dict | None) -> dict:
    if not isinstance(snapshot, dict):
        return {}
    lineage = snapshot.get("lineage")
    return dict(lineage) if isinstance(lineage, dict) else {}


def _evidence_list(records: list) -> list[dict]:
    body = []
    seen = {}
    for record in records:
        seen[str(record.id)] = record
    for record in sorted(seen.values(), key=lambda row: (str(row.id), int(row.year))):
        employee = record.employee
        kpis = [
            {
                "id": str(value.id),
                "kpi_key": value.kpi_key,
                "actual": _canon_decimal(value.actual_value),
                "target": _canon_decimal(value.target_value),
                "achievement": _canon_decimal(value.achievement_ratio),
                "weight": _canon_decimal(value.weight_applied),
                "contribution": _canon_decimal(value.contribution),
            }
            for value in record.kpi_values
        ]
        kpis.sort(key=lambda item: (item["kpi_key"], item["id"]))
        body.append(
            {
                "id": str(record.id),
                "year": int(record.year),
                "month": str(record.month),
                "team_id": str(record.team_id),
                "performance_level": record.performance_level,
                "position_name": record.position_name or "",
                "employee_id": str(record.employee_id),
                "employee_code": getattr(employee, "employee_id", None) if employee is not None else None,
                "branch_key": record.branch_key,
                "region": record.region,
                "upload_id": str(record.upload_id) if record.upload_id else None,
                "uploaded_at": _iso(record.uploaded_at),
                "score": _canon_decimal(record.score),
                "grade": record.grade,
                "status": record.status,
                "payload": _freeze(record.record_payload) if record.record_payload is not None else None,
                "kpis": kpis,
            }
        )
    return body


def _full_snapshot(records: list) -> dict:
    body = _evidence_list(records)
    return {"records": body, "hash": _checksum(body)}


def _source_projection(records: list) -> list[dict]:
    """Identity and workbook inputs. Derived scores are excluded because apply rewrites them."""
    projected = []
    for item in _evidence_list(records):
        projected.append(
            {
                "id": item["id"],
                "year": item["year"],
                "month": item["month"],
                "team_id": item["team_id"],
                "performance_level": item["performance_level"],
                "position_name": item["position_name"],
                "employee_id": item["employee_id"],
                "employee_code": item["employee_code"],
                "branch_key": item["branch_key"],
                "region": item["region"],
                "upload_id": item["upload_id"],
                "uploaded_at": item["uploaded_at"],
                "payload": item["payload"],
                "kpis": [
                    {
                        "id": kpi["id"],
                        "kpi_key": kpi["kpi_key"],
                        "actual": kpi["actual"],
                        "target": kpi["target"],
                    }
                    for kpi in item["kpis"]
                ],
            }
        )
    return projected


def _source_fingerprint(records: list) -> str:
    return _checksum(_source_projection(records))


def _evidence_matches(records: list, snapshot: dict | None) -> bool:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("records"), list):
        return False
    current = _evidence_list(records)
    saved = _freeze(snapshot.get("records"))
    if _checksum(current) != _checksum(saved):
        return False
    stored_hash = snapshot.get("hash")
    if stored_hash is not None and stored_hash != _checksum(saved):
        return False
    if [item["id"] for item in current] != [item["id"] for item in saved]:
        return False
    for left, right in zip(current, saved):
        if [kpi["id"] for kpi in left["kpis"]] != [kpi["id"] for kpi in right["kpis"]]:
            return False
    return True


def _decimal(value):
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _number_or_none(value):
    number = _canon_decimal(value)
    if number is None:
        return None
    return float(Decimal(number))


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


def _saved_applied_basis(record: PerformanceRecord | None) -> dict | None:
    """Return the basis apply saved on this visible row.

    An approved version that was never written onto the row is not a substitute.
    """
    payload = getattr(record, "record_payload", None) if record is not None else None
    if not isinstance(payload, dict):
        return None
    basis = payload.get("evaluation_basis")
    if not isinstance(basis, dict) or basis.get("pinned") is not True:
        return None
    return basis


def _visible_evidence(rows: list[PerformanceRecord], actor: dict, team_name: str) -> list[PerformanceRecord]:
    """Keep rows that pass the canonical team, level, person, branch, function, and region filters."""
    projections = []
    for row in rows:
        employee = getattr(row, "employee", None)
        team = getattr(row, "team", None)
        region = getattr(row, "region", None) or getattr(employee, "region", None) or getattr(team, "region", None)
        projections.append(
            SimpleNamespace(
                team=team_name,
                performance_level=row.performance_level,
                employee_id=str(getattr(employee, "employee_id", "") or ""),
                branch_key=getattr(row, "branch_key", None),
                region=region,
                employee=SimpleNamespace(region=getattr(employee, "region", None)) if employee is not None else None,
            )
        )
    visible = filter_records_by_scope(projections, actor)
    visible = filter_records_by_team_levels(visible, actor)
    allowed = {id(item) for item in visible}
    return [row for row, projection in zip(rows, projections) if id(projection) in allowed]


class EvaluationWorkflow:
    def __init__(self, db: Session):
        self.db = db
        self.catalog = EvaluationCatalog(db)

    def _ready(self) -> None:
        assert_schema(self.db)

    def _require_admin(self, actor: dict) -> None:
        """Management calls stop here, before any catalog sync or settings write."""
        require_action(actor, "", "catalog")

    def _scope(self, scope_id, *, sync: bool = False) -> EvaluationScope:
        self._ready()
        parsed = _as_uuid(scope_id, "Evaluation scope was not found.")
        scope = self.db.query(EvaluationScope).filter(EvaluationScope.id == parsed).one_or_none()
        if scope is None and sync:
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
        self._require_admin(scope)
        self._ready()
        rows = self.catalog.sync()
        visible = [self.catalog.serialize(row) for row in rows]
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
                edit_mode="blocked",
                weight_only_allowed=False,
            )

    def _guard_editable(self, scope_row: EvaluationScope) -> None:
        """Live file audit. Stored readiness and a client weight_only flag are not permission."""
        if scope_row.team_id is not None:
            team = self.db.query(Team).filter(Team.id == scope_row.team_id).one_or_none()
            if team is None or not team.is_active:
                raise EvaluationError(
                    "This team is inactive. It stays outside the supported rollout.",
                    code="scope_blocked",
                    edit_mode="blocked",
                    weight_only_allowed=False,
                )
        decision = self.catalog.decision_for(scope_row)
        if not decision.allows_ratio_edit:
            raise EvaluationError(
                decision.reason,
                code="unsupported_calculation",
                edit_mode="blocked",
                weight_only_allowed=False,
                readiness=scope_row.readiness,
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

    def _insert_version(
        self,
        scope_row: EvaluationScope,
        year: int,
        month: int,
        lines: list[dict],
        status: str,
        notes: str,
        actor: dict,
        snapshot: dict | None = None,
    ) -> TeamConfigurationVersion:
        if scope_row.team_id is None:
            raise EvaluationError("A file-only baseline has no live team to bind.", code="scope_blocked")
        if snapshot is None:
            snapshot = {
                "schema": 1,
                "performance_level": scope_row.performance_level,
                "position_name": scope_row.position_name or "",
                "policy": "employee_ratio",
                "lines": lines,
                "grade_thresholds": self.catalog.thresholds(scope_row),
            }
        else:
            snapshot = dict(snapshot)
            snapshot["lines"] = lines
            snapshot.pop("preview_evidence", None)
        user_id = _actor_id(actor)
        row = TeamConfigurationVersion(
            id=uuid.uuid4(),
            team_id=scope_row.team_id,
            version_number=self._version_number(scope_row.team_id),
            status=status,
            effective_month=month_name(month),
            effective_year=int(year),
            config_snapshot=snapshot,
            config_checksum=_rules_checksum(snapshot),
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
        self._require_admin(actor)
        scope_row = self._scope(scope_id, sync=True)
        self._guard_editable(scope_row)
        self._guard_supported(scope_row)
        number = month_number(month)
        self._lock_team(scope_row.team_id)
        existing = self._find_version(scope_row, int(year), number, "draft")
        if existing and not copy_previous:
            if _lineage(existing.config_snapshot).get("source_version_id"):
                raise EvaluationConflict(
                    "A revision draft already exists for this month. Resume it with revise, not a file draft.",
                    code="draft_exists",
                    draft_id=str(existing.id),
                )
            return self._serialize_version(existing, scope_row)
        approved = self._find_version(scope_row, int(year), number, "approved")
        if approved is not None:
            raise EvaluationConflict(
                "This month already has an approved version. Revise that version instead of starting from the file baseline.",
                code="already_approved",
                version_id=str(approved.id),
            )
        if existing and _lineage(existing.config_snapshot).get("source_version_id"):
            raise EvaluationConflict(
                "A revision draft already exists for this month and was not overwritten.",
                code="draft_exists",
                draft_id=str(existing.id),
            )
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
        self._require_admin(actor)
        self._ready()
        version = self._version(version_id)
        scope_row = self._scope_for_version(version)
        self._guard_editable(scope_row)
        self._guard_supported(scope_row)
        if version.status != "draft":
            raise EvaluationError("Approved settings are immutable. Open a new draft.", code="immutable")
        self._lock_team(version.team_id)
        version = self._version(version.id)
        if version.status != "draft":
            raise EvaluationError("Approved settings are immutable. Open a new draft.", code="immutable")
        cleaned, notes = self._validate_lines(snapshot_lines(version), lines, weight_only=weight_only)
        snapshot = dict(version.config_snapshot or {})
        snapshot.pop("preview_evidence", None)
        snapshot["lines"] = cleaned
        version.config_snapshot = snapshot
        version.config_checksum = _rules_checksum(snapshot)
        flag_modified(version, "config_snapshot")
        if notes:
            version.notes = (version.notes or "") + " " + " ".join(notes)
        self.db.commit()
        body = self._serialize_version(version, scope_row)
        body["diagnostics"] = notes
        return body

    def approve(self, actor: dict, version_id) -> dict:
        self._require_admin(actor)
        self._ready()
        version = self._version(version_id)
        scope_row = self._scope_for_version(version)
        self._guard_editable(scope_row)
        self._guard_supported(scope_row)
        self._lock_team(scope_row.team_id)
        version = self._version(version.id)
        if version.status != "draft":
            raise EvaluationError("Only a draft can be approved.", code="immutable")
        self._validate_lines(snapshot_lines(version), snapshot_lines(version))
        self._assert_proof(version, scope_row)
        current = self._find_version(scope_row, version.effective_from_year, version.effective_from_month, "approved")
        if current is not None and current.id != version.id:
            current.status = "superseded"
            current.superseded_at = _now()
            self.db.flush()
        version.status = "approved"
        version.published_at = _now()
        version.published_by_user_id = _actor_id(actor)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise EvaluationConflict("Another approval already published this scope and month.", code="duplicate_binding") from exc
        self.db.commit()
        self._bump("config")
        body = self._serialize_version(version, scope_row)
        body["applied"] = False
        return body

    def preview(self, actor: dict, version_id, rows: list[dict]) -> dict:
        """Client sample only. It does not store preview_evidence and cannot approve a month."""
        self._require_admin(actor)
        self._ready()
        version = self._version(version_id)
        scope_row = self._scope_for_version(version)
        self._guard_editable(scope_row)
        if version.status not in {"draft", "approved"}:
            raise EvaluationError("Preview needs a draft or approved version.", code="not_found")
        body = score_basis(version, rows)
        body["writes"] = 0
        body["satisfies_approval_gate"] = False
        return body

    def run_preview_job(self, actor: dict, version_id, rows: list[dict]) -> dict:
        """Job entry. The caller's grants are read again here, including after revocation."""
        self._require_admin(actor)
        return self.preview(actor, version_id, rows)

    def export_version(self, actor: dict, version_id) -> dict:
        self._require_admin(actor)
        self._ready()
        version = self._version(version_id)
        scope_row = self._scope_for_version(version)
        return self._serialize_version(version, scope_row)

    def get_version(self, actor: dict, version_id) -> dict:
        self._require_admin(actor)
        self._ready()
        version = self._version(version_id)
        scope_row = self._scope_for_version(version)
        return self._serialize_version(version, scope_row)

    def period(self, actor: dict, scope_id, year: int, month) -> dict:
        self._require_admin(actor)
        scope_row = self._scope(scope_id, sync=True)
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
        scope_row = self._scope(scope_id, sync=False)
        require_action(actor, self._team_name(scope_row), "applied", scope_row.performance_level)
        bodies = []
        for month in months:
            number = month_number(month)
            visible = self._records(scope_row, int(year), number, actor)
            source = visible[0] if visible else None
            basis = _saved_applied_basis(source)
            bodies.append(
                {
                    "year": int(year),
                    "month": number,
                    "month_name": month_name(number),
                    "version_id": None if basis is None else basis.get("version_id"),
                    "lines": [] if basis is None else list(basis.get("lines") or []),
                    "stored_score": None if source is None else float(source.score),
                    "pinned": basis is not None,
                }
            )
        return {"scope_id": str(scope_row.id), "periods": bodies}

    def revise(self, actor: dict, version_id) -> dict:
        """Open a same-month draft from one approved version. The source row stays approved and unchanged."""
        self._require_admin(actor)
        source = self._version(version_id)
        if source.status != "approved":
            raise EvaluationError("Only an approved version can be revised.", code="immutable")
        scope_row = self._scope_for_version(source)
        require_action(actor, self._team_name(scope_row), "approve")
        self._guard_supported(scope_row)
        if not self._is_source_audited(scope_row):
            raise EvaluationError(
                "This scope is outside the source-audited correction rollout.",
                code="scope_blocked",
            )
        year = int(source.effective_from_year)
        month = int(source.effective_from_month)
        source_id = str(source.id)
        self._lock_team(scope_row.team_id)
        source = self._version(source_id)
        if source.status != "approved":
            raise EvaluationError("Only an approved version can be revised.", code="immutable")
        existing = self._find_version(scope_row, year, month, "draft")
        if existing is not None:
            if str(_lineage(existing.config_snapshot).get("source_version_id") or "") == source_id:
                body = self._serialize_version(existing, scope_row)
                body["resumed"] = True
                return body
            raise EvaluationConflict(
                "A draft already exists for this month and was not overwritten.",
                code="draft_exists",
                draft_id=str(existing.id),
            )
        snapshot = self._copied_snapshot(source)
        try:
            created = self._insert_version(
                scope_row,
                year,
                month,
                list(snapshot.get("lines") or []),
                "draft",
                f"Revision of approved version {source_id}.",
                actor,
                snapshot=snapshot,
            )
        except EvaluationError as exc:
            if exc.data.get("code") != "duplicate_binding":
                raise
            existing = self._find_version(scope_row, year, month, "draft")
            if existing is not None and str(_lineage(existing.config_snapshot).get("source_version_id") or "") == source_id:
                body = self._serialize_version(existing, scope_row)
                body["resumed"] = True
                return body
            raise
        self.db.commit()
        body = self._serialize_version(created, scope_row)
        body["resumed"] = False
        return body

    def impact_preview(self, actor: dict, version_id) -> dict:
        """Score every stored record in this scope and month. Client rows are not accepted."""
        self._require_admin(actor)
        version = self._version(version_id)
        scope_row = self._scope_for_version(version)
        require_action(actor, self._team_name(scope_row), "approve")
        self._guard_supported(scope_row)
        if version.status != "draft":
            raise EvaluationError("Impact preview is stored on a draft before approval.", code="immutable")
        self._validate_lines(snapshot_lines(version), snapshot_lines(version))
        self._lock_team(scope_row.team_id)
        version = self._version(version.id)
        if version.status != "draft":
            raise EvaluationError("Impact preview is stored on a draft before approval.", code="immutable")
        records = self._exact_records(scope_row, version.effective_from_year, version.effective_from_month)
        if records and not self._is_source_audited(scope_row):
            raise EvaluationError(
                "This scope is outside the source-audited correction rollout.",
                code="scope_blocked",
            )
        comparisons = []
        conflicts = []
        missing = []
        for record in records:
            record_missing, rows, record_conflicts = self._record_inputs(version, record)
            missing.extend(record_missing)
            conflicts.extend(record_conflicts)
            if record_missing:
                continue
            scored = score_basis(version, rows, check_conflicts=False)
            if scored.get("score") is None or not scored.get("grade"):
                raise EvaluationError(
                    "Stored results could not be scored. Impact preview was not stored.",
                    code="insufficient_data",
                )
            before_kpis = {value.kpi_key: value for value in record.kpi_values}
            comparisons.append(
                {
                    "record_id": str(record.id),
                    "employee_id": str(record.employee_id),
                    "employee_code": getattr(record.employee, "employee_id", None) if record.employee is not None else None,
                    "before_score": float(record.score),
                    "after_score": scored["score"],
                    "before_grade": record.grade,
                    "after_grade": scored["grade"],
                    "kpis": [
                        {
                            "kpi_key": row["kpi_key"],
                            "actual": row.get("actual"),
                            "workbook_target": row.get("workbook_target"),
                            "applied_target": row.get("target"),
                            "weight": row.get("weight"),
                            "before_achievement": _number_or_none(getattr(before_kpis.get(row["kpi_key"]), "achievement_ratio", None)),
                            "after_achievement": row.get("achievement"),
                            "before_contribution": _number_or_none(getattr(before_kpis.get(row["kpi_key"]), "contribution", None)),
                            "after_contribution": row.get("contribution"),
                        }
                        for row in scored["rows"]
                    ],
                }
            )
        if missing:
            raise EvaluationError(
                "A weighted KPI has no stored actual. Impact preview was not stored.",
                code="missing_evidence",
                missing_evidence=missing,
            )
        changed = [
            item for item in comparisons
            if _canon_decimal(item["before_score"]) != _canon_decimal(item["after_score"]) or item["before_grade"] != item["after_grade"]
        ]
        fingerprint = _source_fingerprint(records)
        proof = {
            "scope_id": str(scope_row.id),
            "team_id": str(scope_row.team_id) if scope_row.team_id else None,
            "performance_level": scope_row.performance_level,
            "position_name": scope_row.position_name or "",
            "year": int(version.effective_from_year),
            "month": int(version.effective_from_month),
            "source_fingerprint": fingerprint,
            "affected_count": len(records),
            "scored_employees": len(comparisons),
            "config_validated": True,
        }
        self._store_proof(version, proof)
        self.db.commit()
        stored = (version.config_snapshot or {}).get("preview_evidence") or proof
        return {
            "version_id": str(version.id),
            "scope_id": str(scope_row.id),
            "year": int(version.effective_from_year),
            "month": int(version.effective_from_month),
            "writes": 0,
            "config_validated": True,
            "zero_affected": len(records) == 0,
            "affected_count": len(records),
            "scored_employees": len(comparisons),
            "changed_count": len(changed),
            "unchanged_count": len(comparisons) - len(changed),
            "conflicts": conflicts,
            "missing_evidence": [],
            "comparisons": comparisons,
            "rules_checksum": stored.get("rules_checksum") or version.config_checksum,
            "source_fingerprint": fingerprint,
            "proof_stored": True,
            "satisfies_approval_gate": True,
        }

    def apply(self, actor: dict, scope_id, year: int, month) -> dict:
        self._require_admin(actor)
        scope_row = self._scope(scope_id, sync=True)
        self._guard_editable(scope_row)
        self._guard_supported(scope_row)
        if not self._is_source_audited(scope_row):
            raise EvaluationError(
                "This scope is outside the source-audited correction rollout.",
                code="scope_blocked",
            )
        number = month_number(month)
        self._lock_team(scope_row.team_id)
        version = self._find_version(scope_row, int(year), number, "approved")
        if version is None:
            raise EvaluationError("Approve this month before applying it.", code="not_approved")
        revisions = self._period_revisions(scope_row, int(year), number)
        head = self._head_revision(revisions)
        if head is not None and head.version_id == version.id:
            return self._revision_body(head, idempotent=True)
        try:
            self._assert_proof(version, scope_row)
            records = self._exact_records(scope_row, int(year), number)
            if not records:
                raise EvaluationError(
                    "This period has no stored results to recalculate. Apply is blocked until evidence exists.",
                    code="insufficient_data",
                )
            prior = _full_snapshot(records)
            for record in records:
                self._apply_scores(version, record)
            self.db.flush()
            for record in records:
                for value in list(record.kpi_values):
                    self.db.expire(value)
                self.db.expire(record)
            records = self._exact_records(scope_row, int(year), number)
            applied = _full_snapshot(records)
            applied_rows = [
                {"id": item["id"], "score": float(item["score"]), "grade": item["grade"]}
                for item in applied["records"]
            ]
            for row in revisions:
                if row.status == "active":
                    self._retire_replaced(row)
            revision = EvaluationRevision(
                team_id=scope_row.team_id,
                performance_level=scope_row.performance_level,
                position_name=scope_row.position_name or "",
                year=int(year),
                month=number,
                version_id=version.id,
                status="active",
                previous_revision_id=head.id if head is not None else None,
                prior_snapshot=prior,
                applied_snapshot=applied,
                created_by_user_id=_actor_id(actor),
            )
            self.db.add(revision)
            self.db.flush()
            self.db.commit()
        except EvaluationError:
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            raise EvaluationConflict("Another apply already recorded this revision.", code="duplicate_binding") from exc
        self._bump("data")
        body = self._revision_body(revision, idempotent=False)
        body["records"] = applied_rows
        return body

    def rollback(self, actor: dict, revision_id) -> dict:
        self._require_admin(actor)
        self._ready()
        parsed = _as_uuid(revision_id, "Revision was not found.")
        revision = self.db.query(EvaluationRevision).filter(EvaluationRevision.id == parsed).one_or_none()
        if revision is None:
            raise EvaluationError("Revision was not found.", code="not_found")
        team = self.db.query(Team).filter(Team.id == revision.team_id).one()
        require_action(actor, logical_team_name(team), "rollback")
        self._lock_team(revision.team_id)
        revision = self.db.query(EvaluationRevision).filter(EvaluationRevision.id == parsed).one()
        revisions = self._period_revisions(revision, int(revision.year), int(revision.month))
        if any(row.previous_revision_id == revision.id for row in revisions):
            raise EvaluationConflict(
                "An older revision cannot roll back a newer one.",
                code="not_latest",
            )
        if revision.status != "active":
            raise EvaluationError("Only the active revision can be rolled back.", code="immutable")
        records = self._exact_records(revision, int(revision.year), int(revision.month))
        if not _evidence_matches(records, revision.applied_snapshot):
            raise EvaluationConflict(
                "Stored evidence no longer matches the applied snapshot. Rollback made no changes.",
                code="evidence_changed",
            )
        try:
            restored = self._restore(revision.prior_snapshot)
            revision.status = "rolled_back"
            self.db.flush()
            self.db.commit()
        except EvaluationError:
            self.db.rollback()
            raise
        self._bump("data")
        return {
            "revision_id": str(revision.id),
            "status": "rolled_back",
            "restored_basis": restored,
            "restored_revision_id": None,
        }

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
        team_name = logical_team_name(team)
        require_approved_capability(
            version,
            team_name=team_name,
            config=self.catalog._config_for(team_name),
        )
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
        return _visible_evidence(rows, actor, self._team_name(scope_row))

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

    def _require_admin(self, actor: dict) -> None:
        require_action(actor, "", "catalog")

    def _is_source_audited(self, scope_row: EvaluationScope) -> bool:
        keys = {
            str(scope_row.team_key or "").casefold(),
            str(scope_row.display_name or "").casefold(),
        }
        return (
            scope_row.performance_level == "Employee"
            and (scope_row.position_name or "") == ""
            and bool(keys & AUDITED_SCOPE_KEYS)
        )

    def _lock_team(self, team_id) -> None:
        """Serialize a team on PostgreSQL. SQLite does not support SELECT FOR UPDATE."""
        if team_id is None:
            return
        query = self.db.query(Team).filter(Team.id == team_id)
        bind = self.db.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            query = query.with_for_update()
        query.one_or_none()

    def _allows_superseded(self) -> bool:
        bind = self.db.get_bind()
        dialect = bind.dialect.name if bind is not None else ""
        if dialect == "sqlite":
            row = self.db.execute(
                text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'evaluation_revisions'")
            ).scalar()
            return "superseded" in str(row or "").lower()
        if dialect == "postgresql":
            row = self.db.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname = 'ck_evaluation_revision_status'"
                )
            ).scalar()
            return "superseded" in str(row or "").lower()
        return False

    def _copied_snapshot(self, source: TeamConfigurationVersion) -> dict:
        original = source.config_snapshot if isinstance(source.config_snapshot, dict) else {}
        snapshot = _freeze(original)
        snapshot.pop("preview_evidence", None)
        snapshot["lineage"] = {
            "source_version_id": str(source.id),
            "source_checksum": source.config_checksum,
            "source_version_number": int(source.version_number),
        }
        snapshot.setdefault("lines", _freeze(snapshot_lines(source)))
        snapshot.setdefault("grade_thresholds", {"A": 95, "B": 85, "C": 75, "D": 65})
        snapshot.setdefault("policy", "employee_ratio")
        snapshot.setdefault("schema", 1)
        snapshot["performance_level"] = source.performance_level
        snapshot["position_name"] = source.position_name or ""
        return snapshot

    def _exact_records(self, scope_row, year: int, month: int) -> list[PerformanceRecord]:
        aliases = {item.casefold() for item in month_aliases(month)}
        rows = (
            self.db.query(PerformanceRecord)
            .options(joinedload(PerformanceRecord.kpi_values), joinedload(PerformanceRecord.employee))
            .filter(
                PerformanceRecord.team_id == scope_row.team_id,
                PerformanceRecord.performance_level == scope_row.performance_level,
                PerformanceRecord.year == int(year),
            )
            .all()
        )
        position = scope_row.position_name or ""
        selected = {}
        for row in rows:
            if str(row.month).strip().casefold() not in aliases:
                continue
            if (row.position_name or "") != position:
                continue
            selected[str(row.id)] = row
        return [selected[key] for key in sorted(selected)]

    def _record_inputs(self, version: TeamConfigurationVersion, record: PerformanceRecord) -> tuple[list[dict], list[dict], list[dict]]:
        values_by_key: dict[str, KPIValue] = {}
        for value in record.kpi_values:
            values_by_key.setdefault(value.kpi_key, value)
        missing = []
        rows = []
        conflicts = []
        for line in snapshot_lines(version):
            key = str(line.get("kpi_key"))
            weight = _decimal(line.get("weight")) or Decimal("0")
            value = values_by_key.get(key)
            if weight > 0 and (value is None or value.actual_value is None):
                missing.append(
                    {
                        "record_id": str(record.id),
                        "employee_id": str(record.employee_id),
                        "kpi_key": key,
                        "reason": "missing_weighted_actual",
                    }
                )
                continue
            if value is None:
                continue
            rows.append(
                {
                    "kpi_key": value.kpi_key,
                    "actual": value.actual_value,
                    "workbook_target": value.target_value,
                    "precomputed_achievement": value.achievement_ratio,
                }
            )
            if line.get("target_mode") == "fixed" and line.get("target") is not None and value.target_value is not None:
                workbook = _decimal(value.target_value)
                fixed = _decimal(line.get("target"))
                if workbook is not None and fixed is not None and abs(workbook - fixed) > Decimal("0.0001"):
                    conflicts.append(
                        {
                            "record_id": str(record.id),
                            "employee_id": str(record.employee_id),
                            "kpi_key": key,
                            "workbook_target": float(workbook),
                            "fixed_target": float(fixed),
                            "difference": float(workbook - fixed),
                        }
                    )
        return missing, rows, conflicts

    def _store_proof(self, version: TeamConfigurationVersion, proof: dict) -> None:
        snapshot = dict(version.config_snapshot or {})
        snapshot.pop("preview_evidence", None)
        rules_checksum = _rules_checksum(snapshot)
        stored = dict(proof)
        stored["rules_checksum"] = rules_checksum
        snapshot["preview_evidence"] = stored
        version.config_snapshot = snapshot
        version.config_checksum = rules_checksum
        flag_modified(version, "config_snapshot")

    def _assert_proof(self, version: TeamConfigurationVersion, scope_row: EvaluationScope) -> dict:
        snapshot = version.config_snapshot if isinstance(version.config_snapshot, dict) else {}
        proof = snapshot.get("preview_evidence")
        if not isinstance(proof, dict):
            raise EvaluationConflict(
                "An impact preview of the stored records is required before approval.",
                code="preview_required",
            )
        rules_checksum = _rules_checksum(snapshot)
        if proof.get("rules_checksum") != rules_checksum or version.config_checksum != rules_checksum:
            raise EvaluationConflict(
                "Impact preview is stale because the rules changed.",
                code="stale_preview",
            )
        if str(proof.get("scope_id") or "") != str(scope_row.id):
            raise EvaluationConflict("Impact preview is for a different scope.", code="stale_preview")
        if str(proof.get("team_id") or "") != str(scope_row.team_id or ""):
            raise EvaluationConflict("Impact preview is for a different scope.", code="stale_preview")
        if proof.get("performance_level") != scope_row.performance_level or (proof.get("position_name") or "") != (scope_row.position_name or ""):
            raise EvaluationConflict("Impact preview is for a different scope.", code="stale_preview")
        if int(proof.get("year") or 0) != int(version.effective_from_year) or int(proof.get("month") or 0) != int(version.effective_from_month):
            raise EvaluationConflict("Impact preview is for a different period.", code="stale_preview")
        records = self._exact_records(scope_row, version.effective_from_year, version.effective_from_month)
        if proof.get("source_fingerprint") != _source_fingerprint(records):
            raise EvaluationConflict(
                "Impact preview is stale because stored evidence changed.",
                code="stale_preview",
            )
        return proof

    def _period_revisions(self, scope_row, year: int, month: int) -> list[EvaluationRevision]:
        return (
            self.db.query(EvaluationRevision)
            .filter(
                EvaluationRevision.team_id == scope_row.team_id,
                EvaluationRevision.performance_level == scope_row.performance_level,
                EvaluationRevision.position_name == (scope_row.position_name or ""),
                EvaluationRevision.year == int(year),
                EvaluationRevision.month == int(month),
            )
            .all()
        )

    def _head_revision(self, revisions: list[EvaluationRevision]) -> EvaluationRevision | None:
        referenced = {row.previous_revision_id for row in revisions if row.previous_revision_id is not None}
        heads = [row for row in revisions if row.id not in referenced and row.status == "active"]
        if not heads:
            return None

        def sort_key(row: EvaluationRevision):
            created = row.created_at or datetime.min.replace(tzinfo=timezone.utc)
            return (created, str(row.id))

        return max(heads, key=sort_key)

    def _retire_replaced(self, revision: EvaluationRevision) -> None:
        """Supersede when the schema allows that status. Never label a replaced revision rolled back."""
        if revision.status != "active":
            return
        if self._allows_superseded():
            revision.status = "superseded"

    def _apply_scores(self, version: TeamConfigurationVersion, record: PerformanceRecord) -> dict:
        missing, rows, _conflicts = self._record_inputs(version, record)
        if missing:
            raise EvaluationError(
                "A weighted KPI has no stored actual. Apply is blocked.",
                code="missing_evidence",
                missing_evidence=missing,
            )
        if not rows:
            raise EvaluationError(
                "Stored results have no KPI actuals. Apply is blocked.",
                code="insufficient_data",
            )
        scored = score_basis(version, rows, check_conflicts=False)
        if scored.get("score") is None or not scored.get("grade"):
            raise EvaluationError(
                "Stored results could not be scored. Apply is blocked.",
                code="insufficient_data",
            )
        by_key = {row["kpi_key"]: row for row in scored["rows"]}
        weighted = {
            str(line.get("kpi_key"))
            for line in snapshot_lines(version)
            if (_decimal(line.get("weight")) or Decimal("0")) > 0
        }
        for value in record.kpi_values:
            if value.kpi_key in weighted and value.kpi_key not in by_key:
                raise EvaluationError(
                    "A weighted KPI was not scored. Apply is blocked.",
                    code="missing_evidence",
                    kpi_key=value.kpi_key,
                )
            item = by_key.get(value.kpi_key)
            if item is None:
                continue
            if item.get("target") is None or item.get("achievement") is None or item.get("contribution") is None:
                raise EvaluationError(
                    "Scoring did not return a complete KPI result. Apply is blocked.",
                    code="insufficient_data",
                    kpi_key=value.kpi_key,
                )
            value.target_value = item["target"]
            value.achievement_ratio = item["achievement"]
            value.weight_applied = item["weight"]
            value.contribution = item["contribution"]
        record.score = scored["score"]
        record.grade = scored["grade"]
        record.status = status_for_grade(record.grade)
        payload = dict(record.record_payload or {})
        payload["evaluation_basis"] = basis_payload(version)
        evaluation = dict(payload.get("evaluation") or {})
        evaluation["score"] = float(record.score)
        evaluation["grade"] = record.grade
        payload["evaluation"] = evaluation
        record.record_payload = payload
        flag_modified(record, "record_payload")
        return {"id": str(record.id), "score": float(record.score), "grade": record.grade}

    def _revision_body(self, revision: EvaluationRevision, *, idempotent: bool) -> dict:
        snapshot = revision.applied_snapshot if isinstance(revision.applied_snapshot, dict) else {}
        records = []
        for item in snapshot.get("records") or []:
            if "score" not in item or "grade" not in item:
                continue
            records.append({"id": item["id"], "score": float(item["score"]), "grade": item["grade"]})
        return {
            "revision_id": str(revision.id),
            "version_id": str(revision.version_id),
            "idempotent": idempotent,
            "records": records,
            "snapshot_hash": snapshot.get("hash"),
            "applied_count": len(snapshot.get("records") or []),
        }

    def _restore(self, snapshot: dict) -> list[dict]:
        items = snapshot.get("records") if isinstance(snapshot, dict) else None
        if not isinstance(items, list) or not items:
            raise EvaluationConflict(
                "The prior snapshot has no records to restore.",
                code="evidence_changed",
            )
        restored = []
        for item in items:
            record = (
                self.db.query(PerformanceRecord)
                .filter(PerformanceRecord.id == uuid.UUID(str(item["id"])), PerformanceRecord.year == int(item["year"]))
                .one_or_none()
            )
            if record is None:
                raise EvaluationConflict(
                    "A snapshotted record is missing. Rollback made no changes.",
                    code="evidence_changed",
                    record_id=item.get("id"),
                )
            saved_kpis = list(item.get("kpis") or [])
            by_id = {str(kpi["id"]): kpi for kpi in saved_kpis}
            live_ids = {str(value.id) for value in record.kpi_values}
            if live_ids != set(by_id):
                raise EvaluationConflict(
                    "A snapshotted KPI set does not match the stored record. Rollback made no changes.",
                    code="evidence_changed",
                    record_id=item.get("id"),
                )
            record.score = Decimal(str(item["score"]))
            record.grade = item["grade"]
            record.status = item["status"]
            record.record_payload = item.get("payload")
            flag_modified(record, "record_payload")
            for value in record.kpi_values:
                saved = by_id[str(value.id)]
                for field in ("actual", "target", "achievement", "weight", "contribution"):
                    if saved.get(field) is None:
                        raise EvaluationConflict(
                            "A snapshotted KPI value is incomplete. Rollback made no changes.",
                            code="evidence_changed",
                            record_id=item.get("id"),
                            kpi_id=str(value.id),
                        )
                value.actual_value = Decimal(str(saved["actual"]))
                value.target_value = Decimal(str(saved["target"]))
                value.achievement_ratio = Decimal(str(saved["achievement"]))
                value.weight_applied = Decimal(str(saved["weight"]))
                value.contribution = Decimal(str(saved["contribution"]))
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            restored.append({"record_id": str(record.id), "evaluation_basis": payload.get("evaluation_basis")})
        return restored

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
        snapshot = version.config_snapshot if isinstance(version.config_snapshot, dict) else {}
        lineage = _lineage(snapshot)
        return {
            "id": str(version.id),
            "scope_id": str(scope_row.id),
            "status": version.status,
            "version_number": version.version_number,
            "year": version.effective_from_year,
            "month": version.effective_from_month,
            "month_name": month_name(version.effective_from_month),
            "lines": snapshot_lines(version),
            "grade_thresholds": snapshot.get("grade_thresholds"),
            "notes": version.notes,
            "checksum": version.config_checksum,
            "source_version_id": lineage.get("source_version_id"),
            "source_checksum": lineage.get("source_checksum"),
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
