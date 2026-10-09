"""Draft, approve, preview, upload pin, apply, and rollback for one exact month."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import func, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
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
    User,
)
from services.evaluation.access import AccessDenied, EvaluationError, TargetConflict, require_action
from services.evaluation.catalog import EvaluationCatalog
from services.evaluation.periods import month_aliases, month_name, month_number, previous_period
from services.evaluation.resolver import (
    approved_version,
    assert_schema,
    basis_payload,
    lock_team_rows,
    require_approved_capability,
    schema_ready,
    score_basis,
    snapshot_lines,
)
from services.evaluation.scoring import SUPPORTED_DIRECTIONS, decimal_places
from services.outbound_period_basis import (
    PRODUCTIVITY_KEY,
    SOURCE_TARGETS,
    apply_basis_targets,
    period_capability,
    productivity_actual,
    productivity_target,
)
from utils.performance_status import status_for_grade
from utils.report_scope import filter_records_by_scope, filter_records_by_team_levels
from utils.team_identity import logical_team_name

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationConflict(EvaluationError):
    """Stale proof, evidence drift, or a lifecycle collision. Nothing was written."""

    status_code = 409


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


def _latest_revision(revisions: list) -> EvaluationRevision | None:
    """Follow immutable lineage; timestamps can tie and UUIDs are not ordered."""
    if not revisions:
        return None
    by_id = {row.id: row for row in revisions}
    referenced = {row.previous_revision_id for row in revisions if row.previous_revision_id is not None}
    heads = [row for row in revisions if row.id not in referenced]
    if len(by_id) != len(revisions) or len(heads) != 1:
        raise EvaluationConflict("Revision history is not a single valid chain.", code="invalid_revision_chain")
    visited = set()
    cursor = heads[0]
    while cursor is not None:
        if cursor.id in visited:
            raise EvaluationConflict("Revision history contains a cycle.", code="invalid_revision_chain")
        visited.add(cursor.id)
        previous = cursor.previous_revision_id
        if previous is not None and previous not in by_id:
            raise EvaluationConflict("Revision history is incomplete.", code="invalid_revision_chain")
        cursor = by_id.get(previous)
    if len(visited) != len(revisions):
        raise EvaluationConflict("Revision history is disconnected.", code="invalid_revision_chain")
    return heads[0]


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


def _source_number(value):
    """Return a finite source decimal. Absence is None. NaN and Infinity are refused."""
    if value is None or value == "":
        return None
    if isinstance(value, bool) or isinstance(value, (list, dict)):
        raise EvaluationError("A stored source value is not a finite number.", code="invalid_evidence")
    try:
        number = Decimal(str(value).strip())
    except Exception as exc:
        raise EvaluationError("A stored source value is not a finite number.", code="invalid_evidence") from exc
    if not number.is_finite():
        raise EvaluationError("A stored source value is not a finite number.", code="invalid_evidence")
    return number


def _known_actor(user) -> dict:
    """Audit identity comes from the users row. Caller-supplied names are not stored."""
    if user is None:
        return {"state": "unknown"}
    return {
        "state": "known",
        "user_id": str(user.id),
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
    }


def _payload_dict(record: PerformanceRecord) -> dict:
    payload = record.record_payload
    return dict(payload) if isinstance(payload, dict) else {}


def _captured_source(rows: list[dict]) -> dict:
    """Original workbook or pre-apply SQL inputs. Edited targets are not stored here."""
    origin = (
        "workbook_raw"
        if any(row.get("origin") in {"workbook_raw", "upload_payload"} for row in rows)
        else "sql_before_apply"
    )
    return {
        "version": 1,
        "origin": origin,
        "kpis": {
            str(row["kpi_key"]): {
                "actual": _canon_decimal(row.get("actual")),
                "target": _canon_decimal(row.get("workbook_target")),
            }
            for row in rows
        },
    }


def _retained_source(payload: dict) -> dict | None:
    evidence = payload.get("source_evidence")
    if not isinstance(evidence, dict) or not isinstance(evidence.get("kpis"), dict):
        return None
    parsed = {}
    for key, item in evidence["kpis"].items():
        if not isinstance(item, dict):
            raise EvaluationError("Stored source evidence is incomplete.", code="invalid_evidence", kpi_key=str(key))
        parsed[str(key)] = {
            "actual": _source_number(item.get("actual")),
            "target": _source_number(item.get("target")),
        }
    return parsed


def _is_pinned(payload: dict) -> bool:
    basis = payload.get("evaluation_basis")
    return isinstance(basis, dict) and (basis.get("pinned") is True or bool(basis.get("version_id")))


def _raw_lookup(raw: dict, column: str | None):
    if not isinstance(raw, dict) or not column:
        return False, None
    if column in raw:
        return True, raw.get(column)
    wanted = "".join(character for character in str(column).casefold() if character.isalnum())
    if not wanted:
        return False, None
    for key, value in raw.items():
        current = "".join(character for character in str(key).casefold() if character.isalnum())
        if current == wanted:
            return True, value
    return False, None


def _config_source(config: dict | None, key: str, raw) -> tuple[bool, Decimal | None, bool, Decimal | None]:
    """Map one KPI through the checked-in actual/target columns. No formula is invented."""
    if not isinstance(raw, dict) or not isinstance(config, dict):
        return False, None, False, None
    matches = [item for item in config.get("kpis") or [] if str(item.get("key") or "") == key]
    if len(matches) > 1:
        raise EvaluationError("The team file repeats a KPI key.", code="duplicate_kpi", kpi_key=key)
    if len(matches) != 1:
        return False, None, False, None
    kpi = matches[0]
    actual_found, actual_raw = _raw_lookup(raw, kpi.get("actual_col"))
    target_found, target_raw = _raw_lookup(raw, kpi.get("target_col"))
    if not actual_found and not target_found:
        return False, None, False, None
    actual = _source_number(actual_raw) if actual_found else None
    target = _source_number(target_raw) if target_found else None
    return actual_found, actual, target_found, target


def _weighted_keys(lines) -> set[str]:
    found = set()
    for line in lines or []:
        key = str(line.get("kpi_key") or "")
        if not key:
            continue
        try:
            weight = Decimal(str(line.get("weight")))
        except Exception:
            continue
        if weight > 0:
            found.add(key)
    return found


def _has_raw_workbook(raw) -> bool:
    """True when raw_data carries a workbook cell. An empty object is not a workbook."""
    if not isinstance(raw, dict) or not raw:
        return False
    for value in raw.values():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return True
    return False


def _productivity_from_raw(record, raw) -> tuple[bool, Decimal | None, bool, Decimal | None]:
    """Full-precision Productivity actual and target. Available Time is not an alias.

    An explicit source target wins. July and August use the audited source target
    only when the actual is present and the workbook has no target column.
    """
    if not isinstance(raw, dict):
        return False, None, False, None
    actual_raw = productivity_actual(raw)
    explicit = productivity_target(raw, None)
    if actual_raw is None and explicit is None:
        return False, None, False, None
    actual = _source_number(actual_raw) if actual_raw is not None else None
    if explicit is not None:
        return True, actual, True, _source_number(explicit)
    basis = period_capability(getattr(record, "year", None), getattr(record, "month", None))
    if actual is not None and apply_basis_targets(basis):
        return True, actual, True, _source_number(SOURCE_TARGETS[PRODUCTIVITY_KEY])
    return True, actual, False, None


def _listed_kpis(payload: dict) -> dict[str, dict]:
    """Payload KPI list from the upload DTO. A historical dict is not an actual source."""
    listed = payload.get("kpi_values")
    if not isinstance(listed, list):
        return {}
    found = {}
    for item in listed:
        if isinstance(item, dict) and item.get("kpi_key"):
            found[str(item.get("kpi_key"))] = item
    return found


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


def _row_basis_signature(record: PerformanceRecord) -> tuple:
    basis = _saved_applied_basis(record)
    if basis is None:
        return ("legacy",)
    return ("pinned", str(basis.get("version_id")), _checksum(list(basis.get("lines") or [])))


def _row_basis_evidence(record: PerformanceRecord) -> dict:
    basis = _saved_applied_basis(record)
    return {
        "record_id": str(record.id),
        "pinned": basis is not None,
        "legacy": basis is None,
        "version_id": None if basis is None else basis.get("version_id"),
        "lines": [] if basis is None else list(basis.get("lines") or []),
        "score": None if record.score is None else float(record.score),
    }


def _saved_period_read(year: int, month: int, visible: list[PerformanceRecord]) -> dict:
    """Report saved pins on the authorized rows only.

    One shared signature describes the saved basis. Only a single-row result
    has a stored_score; multiple people expose their own scores in evidence,
    never the first person's score as a fabricated scope aggregate.
    """
    evidence = [_row_basis_evidence(row) for row in visible]
    body = {
        "year": int(year),
        "month": int(month),
        "month_name": month_name(month),
        "version_id": None,
        "lines": [],
        "stored_score": None,
        "pinned": False,
        "basis_state": "empty" if not visible else "legacy",
        "evidence": evidence,
    }
    if not visible:
        return body
    if len({_row_basis_signature(row) for row in visible}) != 1:
        body["basis_state"] = "mixed"
        return body
    source = visible[0]
    basis = _saved_applied_basis(source)
    if len(visible) == 1:
        body["stored_score"] = None if source.score is None else float(source.score)
    if basis is None:
        body["basis_state"] = "legacy"
        return body
    body["basis_state"] = "pinned"
    body["pinned"] = True
    body["version_id"] = basis.get("version_id")
    body["lines"] = list(basis.get("lines") or [])
    return body


class EvaluationWorkflow:
    def __init__(self, db: Session):
        self.db = db
        self.catalog = EvaluationCatalog(db)

    def _ready(self) -> None:
        assert_schema(self.db)

    def _require_admin(self, actor: dict) -> None:
        """Management calls stop here, before any catalog sync or settings write."""
        require_action(actor, "", "catalog")
        user = self._audit_user(actor)
        if user is None or user.role != "Admin" or user.is_active is not True:
            raise AccessDenied("Evaluation settings are limited to Admin.")

    def _audit_user(self, actor: dict):
        raw = (actor or {}).get("user_id")
        if raw is None or str(raw).strip() == "":
            return None
        try:
            parsed = uuid.UUID(str(raw))
        except (TypeError, ValueError, AttributeError):
            return None
        return self.db.query(User).populate_existing().filter(User.id == parsed).one_or_none()

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

    def _guard_period(self, scope_row: EvaluationScope, year: int, month: int) -> None:
        """Live exact-month capability. Stored readiness is not permission.

        An admitted July or August Outbound month stays editable while the global
        catalog row stays blocked. An unaudited scope stays blocked even when the
        stored row says supported. The team must still be active.
        """
        if scope_row.team_id is not None:
            self._lock_team(scope_row.team_id)
            team = self.db.query(Team).populate_existing().filter(Team.id == scope_row.team_id).one_or_none()
            if team is None or team.is_active is not True:
                raise EvaluationError(
                    "This team is inactive. It stays outside the supported rollout.",
                    code="scope_blocked",
                    edit_mode="blocked",
                    weight_only_allowed=False,
                )
        decision = self.catalog.decision_for(scope_row, int(year), int(month))
        if not decision.allows_ratio_edit:
            raise EvaluationError(
                decision.reason,
                code="unsupported_calculation",
                edit_mode="blocked",
                weight_only_allowed=False,
                readiness=scope_row.readiness,
            )

    def _candidate_version(self, scope_row: EvaluationScope, year: int, month: int, lines: list[dict], snapshot: dict | None = None) -> TeamConfigurationVersion:
        """Unsaved version used to gate a candidate before it is written."""
        body = dict(snapshot or {})
        body.pop("preview_evidence", None)
        body["lines"] = list(lines)
        body.setdefault("policy", "employee_ratio")
        number = int(month)
        return TeamConfigurationVersion(
            id=uuid.uuid4(),
            team_id=scope_row.team_id,
            version_number=0,
            status="draft",
            effective_month=month_name(number),
            effective_year=int(year),
            config_snapshot=body,
            config_checksum=_rules_checksum(body),
            effective_from_month=number,
            effective_from_year=int(year),
            effective_until_month=number,
            effective_until_year=int(year),
            performance_level=scope_row.performance_level,
            position_name=scope_row.position_name or "",
        )

    def _require_lines(self, scope_row: EvaluationScope, year: int, month: int, lines: list[dict], snapshot: dict | None = None) -> None:
        candidate = self._candidate_version(scope_row, year, month, lines, snapshot)
        team_name = self._team_name(scope_row)
        require_approved_capability(
            candidate,
            team_name=team_name,
            config=self.catalog._config_for(team_name),
            year=int(year),
            month=int(month),
        )

    def _require_version(self, scope_row: EvaluationScope, version: TeamConfigurationVersion) -> None:
        team_name = self._team_name(scope_row)
        require_approved_capability(
            version,
            team_name=team_name,
            config=self.catalog._config_for(team_name),
            year=version.effective_from_year,
            month=version.effective_from_month,
        )

    def _validate_lines(self, current: list[dict], proposed: list[dict], *, weight_only: bool = False) -> tuple[list[dict], list[str]]:
        current_by_key = {str(line["kpi_key"]): line for line in current}
        proposed_keys = [str(line.get("kpi_key")) for line in proposed]
        if len(proposed_keys) != len(set(proposed_keys)):
            raise EvaluationError("A draft cannot repeat a KPI key.", code="duplicate_kpi")
        if set(proposed_keys) != set(current_by_key):
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
        user = self._audit_user(actor)
        user_id = user.id if user is not None else None
        actor_snapshot = _known_actor(user)
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
            actor_created_snapshot=actor_snapshot,
            actor_published_snapshot=actor_snapshot if status == "approved" else {"state": "unknown"},
        )
        self.db.add(row)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise EvaluationError("A binding for this scope and month is already active.", code="duplicate_binding") from exc
        return row

    def _find_version(self, scope_row: EvaluationScope, year: int, month: int, status: str, *, lock: bool = False) -> TeamConfigurationVersion | None:
        query = self.db.query(TeamConfigurationVersion).filter(
            TeamConfigurationVersion.team_id == scope_row.team_id,
            TeamConfigurationVersion.performance_level == scope_row.performance_level,
            TeamConfigurationVersion.position_name == (scope_row.position_name or ""),
            TeamConfigurationVersion.effective_from_year == int(year),
            TeamConfigurationVersion.effective_from_month == month,
            TeamConfigurationVersion.status == status,
        )
        return self._for_update(query, lock).one_or_none()

    def open_draft(self, actor: dict, scope_id, year: int, month, *, copy_previous: bool = False) -> dict:
        self._require_admin(actor)
        scope_row = self._scope(scope_id, sync=True)
        number = month_number(month)
        self._guard_period(scope_row, int(year), number)
        existing = self._find_version(scope_row, int(year), number, "draft", lock=True)
        if existing is not None:
            if copy_previous or _lineage(existing.config_snapshot).get("source_version_id"):
                raise EvaluationConflict(
                    "A draft already exists for this month and was left unchanged.",
                    code="draft_exists",
                    draft_id=str(existing.id),
                )
            return self._serialize_version(existing, scope_row)
        approved = self._find_version(scope_row, int(year), number, "approved", lock=True)
        if approved is not None:
            raise EvaluationConflict(
                "This month already has an approved version. Revise that version instead of starting from the file baseline.",
                code="already_approved",
                version_id=str(approved.id),
            )
        snapshot = None
        if copy_previous:
            prior_year, prior_month = previous_period(int(year), number)
            source = self._find_version(scope_row, prior_year, prior_month, "approved")
            copied = _copy_lines(snapshot_lines(source)) if source else []
            reconciled = self.catalog.reconcile_period_lines(scope_row, int(year), number, copied)
            destination = self.catalog.baseline_lines(scope_row, int(year), number)
            source_baseline = self.catalog.baseline_lines(scope_row, prior_year, prior_month) if source else []
            template_shift = bool(source) and _weighted_keys(source_baseline) != _weighted_keys(destination)
            if not copied or template_shift:
                lines = list(reconciled["lines"])
                diagnostics = list(reconciled.get("diagnostics") or [])
                preserved = False if template_shift else bool(reconciled.get("preserved_values"))
                template_changed = bool(reconciled.get("template_changed")) or template_shift
            elif reconciled.get("preserved_values"):
                lines = list(reconciled["lines"])
                diagnostics = list(reconciled.get("diagnostics") or [])
                preserved = True
                template_changed = bool(reconciled.get("template_changed"))
            else:
                # Canonical keys match, but the admin weighted set does not. Keep the selected lines.
                lines = copied
                diagnostics = []
                preserved = True
                template_changed = False
            note = "Copied from the approved previous month." if source else "No approved previous month. Draft started from the file baseline."
            if diagnostics:
                note = note + " " + " ".join(str(item) for item in diagnostics)
            snapshot = {
                "schema": 1,
                "performance_level": scope_row.performance_level,
                "position_name": scope_row.position_name or "",
                "policy": "employee_ratio",
                "lines": lines,
                "grade_thresholds": self.catalog.thresholds(scope_row),
                "copy_diagnostics": diagnostics,
                "template_changed": template_changed,
                "preserved_values": preserved,
                "period_status": reconciled.get("period_status"),
            }
        else:
            lines = self.catalog.baseline_lines(scope_row, int(year), number)
            note = "Draft started from the file baseline."
        if not lines:
            raise EvaluationError("This scope has no KPI baseline to draft.", code="scope_blocked")
        self._require_lines(scope_row, int(year), number, lines, snapshot)
        created = self._insert_version(scope_row, int(year), number, lines, "draft", note, actor, snapshot=snapshot)
        self.db.commit()
        return self._serialize_version(created, scope_row)

    def edit_draft(self, actor: dict, version_id, lines: list[dict], *, weight_only: bool = False, expected_checksum: str | None = None, require_precondition: bool = False) -> dict:
        self._require_admin(actor)
        # HTTP callers must pin the rules they edited. Internal trusted callers
        # retain their existing contract; supplying a checksum also checks it.
        if require_precondition and not expected_checksum:
            raise EvaluationConflict(
                "Load this draft before saving it. A rules checksum is required.",
                code="draft_precondition_required",
            )
        self._ready()
        version = self._version(version_id)
        scope_row = self._scope_for_version(version)
        self._guard_period(scope_row, version.effective_from_year, version.effective_from_month)
        if version.status != "draft":
            raise EvaluationError("Approved settings are immutable. Open a new draft.", code="immutable")
        version = self._version(version.id, lock=True)
        if version.status != "draft":
            raise EvaluationError("Approved settings are immutable. Open a new draft.", code="immutable")
        if expected_checksum is not None and expected_checksum != version.config_checksum:
            raise EvaluationConflict(
                "This draft changed after you opened it. Reload the draft before saving; no changes were made.",
                code="stale_draft",
            )
        cleaned, notes = self._validate_lines(snapshot_lines(version), lines, weight_only=weight_only)
        snapshot = dict(version.config_snapshot or {})
        snapshot.pop("preview_evidence", None)
        self._require_lines(scope_row, version.effective_from_year, version.effective_from_month, cleaned, snapshot)
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
        self._guard_period(scope_row, version.effective_from_year, version.effective_from_month)
        version = self._version(version.id, lock=True)
        if version.status != "draft":
            raise EvaluationError("Only a draft can be approved.", code="immutable")
        self._validate_lines(snapshot_lines(version), snapshot_lines(version))
        self._require_version(scope_row, version)
        self._assert_proof(version, scope_row, lock=True)
        current = self._find_version(scope_row, version.effective_from_year, version.effective_from_month, "approved", lock=True)
        if current is not None and current.id != version.id:
            current.status = "superseded"
            current.superseded_at = _now()
            self.db.flush()
        publisher = self._audit_user(actor)
        version.actor_published_snapshot = _known_actor(publisher)
        version.status = "approved"
        version.published_at = _now()
        version.published_by_user_id = publisher.id if publisher is not None else None
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
        self._guard_period(scope_row, version.effective_from_year, version.effective_from_month)
        if version.status not in {"draft", "approved"}:
            raise EvaluationError("Preview needs a draft or approved version.", code="not_found")
        self._require_version(scope_row, version)
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
        scope_row = self._scope(scope_id, sync=False)
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
        if self._has_revision_table():
            revisions = self._period_revisions(scope_row, int(year), number, lock=False)
            records = self._exact_records(scope_row, int(year), number, lock=False)
        else:
            revisions = []
            records = []
        return {
            "scope": self.catalog.serialize(scope_row, int(year), number),
            "year": int(year),
            "month": number,
            "month_name": month_name(number),
            "versions": [self._serialize_version(row, scope_row) for row in rows],
            "revisions": [self._public_revision(row, revisions, records) for row in sorted(revisions, key=lambda item: (_iso(item.created_at) or "", str(item.id)))],
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
            bodies.append(_saved_period_read(int(year), number, visible))
        return {"scope_id": str(scope_row.id), "periods": bodies}

    def revise(self, actor: dict, version_id) -> dict:
        """Open a same-month draft from one approved version. The source row stays approved and unchanged."""
        self._require_admin(actor)
        source = self._version(version_id)
        if source.status != "approved":
            raise EvaluationError("Only an approved version can be revised.", code="immutable")
        scope_row = self._scope_for_version(source)
        require_action(actor, self._team_name(scope_row), "approve")
        year = int(source.effective_from_year)
        month = int(source.effective_from_month)
        self._guard_period(scope_row, year, month)
        source_id = str(source.id)
        source = self._version(source_id, lock=True)
        if source.status != "approved":
            raise EvaluationError("Only an approved version can be revised.", code="immutable")
        existing = self._find_version(scope_row, year, month, "draft", lock=True)
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
        self._require_lines(scope_row, year, month, list(snapshot.get("lines") or []), snapshot)
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
            existing = self._find_version(scope_row, year, month, "draft", lock=True)
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
        self._guard_period(scope_row, version.effective_from_year, version.effective_from_month)
        if version.status != "draft":
            raise EvaluationError("Impact preview is stored on a draft before approval.", code="immutable")
        self._validate_lines(snapshot_lines(version), snapshot_lines(version))
        version = self._version(version.id, lock=True)
        if version.status != "draft":
            raise EvaluationConflict(
                "Impact preview found a version that is no longer a draft.",
                code="stale_preview",
            )
        records = self._exact_records(scope_row, version.effective_from_year, version.effective_from_month, lock=True)
        self._require_version(scope_row, version)
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
            "comparisons": comparisons,
            "conflicts": conflicts,
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
        number = month_number(month)
        self._guard_period(scope_row, int(year), number)
        version = self._find_version(scope_row, int(year), number, "approved", lock=True)
        if version is None:
            raise EvaluationError("Approve this month before applying it.", code="not_approved")
        revisions = self._period_revisions(scope_row, int(year), number, lock=True)
        records = self._exact_records(scope_row, int(year), number, lock=True)
        active_same = [row for row in revisions if row.status == "active" and row.version_id == version.id]
        if len(active_same) == 1 and not any(row.status == "active" and row.id != active_same[0].id for row in revisions):
            if _evidence_matches(records, active_same[0].applied_snapshot):
                return self._revision_body(active_same[0], idempotent=True)
            raise EvaluationConflict(
                "Stored evidence no longer matches the applied snapshot. Apply made no changes.",
                code="evidence_changed",
            )
        try:
            self._require_version(scope_row, version)
            self._assert_proof(version, scope_row, lock=True)
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
            records = self._exact_records(scope_row, int(year), number, lock=True)
            applied = _full_snapshot(records)
            applied_rows = [
                {"id": item["id"], "score": float(item["score"]), "grade": item["grade"]}
                for item in applied["records"]
            ]
            for row in revisions:
                if row.status == "active":
                    row.status = "superseded"
            self.db.flush()
            latest = _latest_revision(revisions)
            publisher = self._audit_user(actor)
            revision = EvaluationRevision(
                team_id=scope_row.team_id,
                performance_level=scope_row.performance_level,
                position_name=scope_row.position_name or "",
                year=int(year),
                month=number,
                version_id=version.id,
                status="active",
                previous_revision_id=latest.id if latest is not None else None,
                prior_snapshot=prior,
                applied_snapshot=applied,
                created_by_user_id=publisher.id if publisher is not None else None,
                actor_snapshot=_known_actor(publisher),
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
        revision = self._for_update(
            self.db.query(EvaluationRevision).filter(EvaluationRevision.id == parsed),
            True,
        ).one()
        if revision.status == "rolled_back":
            raise EvaluationError("A rolled-back revision stays rolled back.", code="immutable")
        revisions = self._period_revisions(revision, int(revision.year), int(revision.month), lock=True)
        active = [row for row in revisions if row.status == "active"]
        referenced = any(row.previous_revision_id == revision.id for row in revisions)
        if revision.status != "active" or referenced or len(active) != 1 or active[0].id != revision.id:
            raise EvaluationConflict(
                "An older revision cannot roll back a newer one.",
                code="not_latest",
            )
        records = self._exact_records(revision, int(revision.year), int(revision.month), lock=True)
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

    def _upload_config(self, team: Team, record: PerformanceRecord) -> dict | None:
        """Checked-in columns for this upload. Does not query, so an unpersisted record is not flushed."""
        from config.loader import ConfigurationError, resolve_team_config

        config = self.catalog._config_for(logical_team_name(team))
        if not isinstance(config, dict):
            return None
        position = getattr(record, "position_name", None) or None
        if isinstance(position, str) and not position.strip():
            position = None
        level = getattr(record, "performance_level", None) or "Employee"
        try:
            return resolve_team_config(config, level, position)
        except (ConfigurationError, ValueError):
            return None

    def _upload_rows(self, record: PerformanceRecord, team: Team, fresh: list[KPIValue]) -> list[dict]:
        """Full-precision pin inputs. Rounded KPI columns are the last fallback."""
        payload = _payload_dict(record)
        raw = payload.get("raw_data") if isinstance(payload.get("raw_data"), dict) else None
        listed = _listed_kpis(payload)
        config = self._upload_config(team, record)
        rows = []
        for value in fresh:
            key = str(value.kpi_key)
            origin = "kpi_value"
            actual = None
            workbook = None
            found = False
            if key == PRODUCTIVITY_KEY:
                actual_found, raw_actual, target_found, raw_target = _productivity_from_raw(record, raw)
            else:
                actual_found, raw_actual, target_found, raw_target = _config_source(config, key, raw)
            if actual_found or target_found:
                origin = "workbook_raw"
                actual = raw_actual
                workbook = raw_target
                found = True
            if not found:
                item = listed.get(key)
                if item is not None:
                    actual = _source_number(item.get("actual_value", item.get("actual")))
                    workbook = _source_number(item.get("target_value", item.get("workbook_target", item.get("target"))))
                    if actual is not None or workbook is not None:
                        origin = "upload_payload"
                        found = True
            if not found:
                actual = _source_number(value.actual_value)
                workbook = _source_number(value.target_value)
            rows.append(
                {
                    "kpi_key": key,
                    "actual": actual,
                    "workbook_target": workbook,
                    "precomputed_achievement": value.achievement_ratio,
                    "origin": origin,
                }
            )
        return rows

    def rescore_uploaded(self, record: PerformanceRecord, team: Team, values: list[KPIValue], start: int) -> None:
        """Pin an approved basis onto rows the upload is about to save. No basis leaves the rows unchanged.

        Scoring uses the same full-precision workbook evidence as the upload pin.
        Original targets are stored before KPI targets are replaced. raw_data stays
        untouched. Rounded KPI columns are not a second scoring pass.
        """
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
            year=record.year,
            month=record.month,
        )
        fresh = values[start:]
        if not fresh:
            return
        rows = self._upload_rows(record, team, fresh)
        scored = score_basis(version, rows)
        by_key = {item["kpi_key"]: item for item in scored["rows"]}
        payload = dict(record.record_payload or {})
        if _retained_source(payload) is None:
            payload["source_evidence"] = _captured_source(rows)
        payload["evaluation_basis"] = scored["basis"]
        for value in fresh:
            item = by_key.get(value.kpi_key)
            if item is None:
                continue
            weight = item.get("weight") or 0
            if weight > 0 and (item.get("achievement") is None or item.get("contribution") is None or item.get("actual") is None):
                raise EvaluationError(
                    "A weighted KPI has no stored actual. The upload was not pinned.",
                    code="missing_actual",
                    kpi_key=value.kpi_key,
                )
            if item.get("target") is not None:
                value.target_value = item["target"]
            value.achievement_ratio = item["achievement"] if item["achievement"] is not None else 0
            value.weight_applied = item["weight"]
            value.contribution = item["contribution"] if item["contribution"] is not None else 0
        record.record_payload = payload
        flag_modified(record, "record_payload")

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
        if len(rows) != 1 or rows[0].score is None:
            return None
        return float(rows[0].score)

    def _stored_actuals(self, scope_row: EvaluationScope, year: int, month: int, actor: dict) -> dict:
        """Single-person actuals only; do not invent an aggregate from one row."""
        rows = self._records(scope_row, year, month, actor)
        if len(rows) != 1:
            return {}
        actuals = {}
        for value in rows[0].kpi_values:
            if value.actual_value is None:
                continue
            actuals[value.kpi_key] = float(value.actual_value)
        return actuals

    def _for_update(self, query, lock: bool):
        """Refresh identity-map rows. PostgreSQL also takes the row lock; SQLite cannot."""
        query = query.populate_existing()
        bind = self.db.get_bind()
        if lock and bind is not None and bind.dialect.name == "postgresql":
            query = query.with_for_update()
        return query

    def _lock_team(self, team_id) -> None:
        """Same ordered team lock as the upload pin. SQLite runs the read without a row lock."""
        if team_id is None:
            return
        lock_team_rows(self.db, [team_id])

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

    def _exact_records(self, scope_row, year: int, month: int, *, lock: bool = False) -> list[PerformanceRecord]:
        aliases = [item.casefold() for item in month_aliases(month)]
        position = scope_row.position_name or ""
        query = (
            self.db.query(PerformanceRecord)
            .options(
                selectinload(PerformanceRecord.kpi_values),
                selectinload(PerformanceRecord.employee),
            )
            .filter(
                PerformanceRecord.team_id == scope_row.team_id,
                PerformanceRecord.performance_level == scope_row.performance_level,
                PerformanceRecord.year == int(year),
                func.lower(PerformanceRecord.month).in_(aliases),
                func.coalesce(PerformanceRecord.position_name, "") == position,
            )
            .order_by(PerformanceRecord.id)
        )
        records = self._for_update(query, lock).all()
        bind = self.db.get_bind()
        if lock and records and bind is not None and bind.dialect.name == "postgresql":
            self._for_update(
                self.db.query(KPIValue)
                .filter(
                    KPIValue.record_id.in_([row.id for row in records]),
                    KPIValue.record_year == int(year),
                )
                .order_by(KPIValue.id),
                True,
            ).all()
        selected = {}
        for row in records:
            selected[str(row.id)] = row
        return [selected[key] for key in sorted(selected)]

    def _team_file(self, record: PerformanceRecord) -> dict | None:
        team = self.db.query(Team).filter(Team.id == record.team_id).one_or_none()
        if team is None:
            return None
        try:
            from config.loader import load_team_config, resolve_team_config

            config = load_team_config(logical_team_name(team))
            return resolve_team_config(config, record.performance_level, record.position_name or None)
        except Exception:
            return None

    def _record_inputs(self, version: TeamConfigurationVersion, record: PerformanceRecord) -> tuple[list[dict], list[dict], list[dict]]:
        values_by_key: dict[str, KPIValue] = {}
        for value in record.kpi_values:
            key = str(value.kpi_key)
            if key in values_by_key:
                raise EvaluationError(
                    "A stored record repeats a KPI key.",
                    code="duplicate_kpi",
                    record_id=str(record.id),
                    kpi_key=key,
                )
            values_by_key[key] = value
        payload = _payload_dict(record)
        retained = _retained_source(payload)
        pinned = _is_pinned(payload)
        raw = payload.get("raw_data") if isinstance(payload.get("raw_data"), dict) else None
        config = None if retained is not None else self._team_file(record)
        missing = []
        rows = []
        conflicts = []
        for line in snapshot_lines(version):
            key = str(line.get("kpi_key"))
            weight = _decimal(line.get("weight")) or Decimal("0")
            sql_value = values_by_key.get(key)
            origin = "sql_before_apply"
            actual = None
            workbook = None
            if retained is not None:
                origin = "retained"
                item = retained.get(key)
                if item is not None:
                    actual = item["actual"]
                    workbook = item["target"]
            else:
                if key == PRODUCTIVITY_KEY:
                    actual_found, raw_actual, target_found, raw_target = _productivity_from_raw(record, raw)
                else:
                    actual_found, raw_actual, target_found, raw_target = _config_source(config, key, raw)
                workbook_present = key == PRODUCTIVITY_KEY and _has_raw_workbook(raw)
                if actual_found or target_found:
                    origin = "workbook_raw"
                    actual = raw_actual
                    workbook = raw_target
                elif pinned or workbook_present:
                    origin = "missing_pinned" if pinned else "missing_source"
                elif sql_value is not None:
                    actual = _source_number(sql_value.actual_value)
                    workbook = _source_number(sql_value.target_value)
            if weight > 0 and actual is None:
                missing.append(
                    {
                        "record_id": str(record.id),
                        "employee_id": str(record.employee_id),
                        "kpi_key": key,
                        "reason": "missing_source" if origin != "sql_before_apply" else "missing_weighted_actual",
                    }
                )
                continue
            if actual is None and workbook is None:
                continue
            rows.append(
                {
                    "kpi_key": key,
                    "actual": actual,
                    "workbook_target": workbook,
                    "origin": origin,
                }
            )
            if line.get("target_mode") == "fixed" and line.get("target") is not None and workbook is not None:
                fixed = _decimal(line.get("target"))
                if fixed is not None and abs(workbook - fixed) > Decimal("0.0001"):
                    conflicts.append(
                        {
                            "record_id": str(record.id),
                            "employee_id": str(record.employee_id),
                            "kpi_key": key,
                            "workbook_target": float(workbook),
                            "fixed_target": float(fixed),
                            "approved_target": float(fixed),
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

    def _assert_proof(self, version: TeamConfigurationVersion, scope_row: EvaluationScope, *, lock: bool = False) -> dict:
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
        records = self._exact_records(scope_row, version.effective_from_year, version.effective_from_month, lock=lock)
        if proof.get("source_fingerprint") != _source_fingerprint(records):
            raise EvaluationConflict(
                "Impact preview is stale because stored evidence changed.",
                code="stale_preview",
            )
        return proof

    def _has_revision_table(self) -> bool:
        """Partial fixtures can read a period before the revision table exists."""
        inspector = inspect(self.db.connection())
        inspector.clear_cache()
        return EvaluationRevision.__tablename__ in set(inspector.get_table_names())

    def _period_revisions(self, scope_row, year: int, month: int, *, lock: bool = False) -> list[EvaluationRevision]:
        query = self.db.query(EvaluationRevision).filter(
            EvaluationRevision.team_id == scope_row.team_id,
            EvaluationRevision.performance_level == scope_row.performance_level,
            EvaluationRevision.position_name == (scope_row.position_name or ""),
            EvaluationRevision.year == int(year),
            EvaluationRevision.month == int(month),
        )
        return self._for_update(query, lock).all()

    def _public_revision(self, revision: EvaluationRevision, revisions: list[EvaluationRevision], records: list) -> dict:
        snapshot = revision.applied_snapshot if isinstance(revision.applied_snapshot, dict) else {}
        affected = snapshot.get("records")
        latest = _latest_revision(revisions)
        active = [row for row in revisions if row.status == "active"]
        can_rollback = bool(
            revision.status == "active"
            and latest is not None
            and latest.id == revision.id
            and len(active) == 1
            and active[0].id == revision.id
            and _evidence_matches(records, revision.applied_snapshot)
        )
        return {
            "id": str(revision.id),
            "version_id": str(revision.version_id),
            "status": revision.status,
            "created_at": _iso(revision.created_at),
            "affected_count": len(affected) if isinstance(affected, list) else 0,
            "can_rollback": can_rollback,
        }

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
        payload = dict(record.record_payload or {})
        if _retained_source(payload) is None:
            payload["source_evidence"] = _captured_source(rows)
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

    def _version(self, version_id, *, lock: bool = False) -> TeamConfigurationVersion:
        self._ready()
        try:
            parsed = uuid.UUID(str(version_id))
        except ValueError as exc:
            raise EvaluationError("Version was not found.", code="not_found") from exc
        version = self._for_update(
            self.db.query(TeamConfigurationVersion).filter(TeamConfigurationVersion.id == parsed),
            lock,
        ).one_or_none()
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
        proof = snapshot.get("preview_evidence")
        summary = None
        if isinstance(proof, dict):
            summary = {
                "rules_checksum": proof.get("rules_checksum"),
                "source_fingerprint": proof.get("source_fingerprint"),
                "affected_count": proof.get("affected_count"),
                "scored_employees": proof.get("scored_employees"),
                "year": proof.get("year"),
                "month": proof.get("month"),
            }
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
            "source_version_number": lineage.get("source_version_number"),
            "source_checksum": lineage.get("source_checksum"),
            "proof": summary,
        }

    def _bump(self, kind: str) -> None:
        try:
            from services.cache_invalidation_service import CacheInvalidationService

            if kind == "data":
                CacheInvalidationService.bump_data_version()
            else:
                CacheInvalidationService.bump_config_version()
        except Exception:
            logger.warning("Evaluation cache bump failed for kind=%s", kind)
