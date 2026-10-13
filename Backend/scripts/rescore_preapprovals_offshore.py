"""Re-score stored Pre-Approvals IP Offshore months with the June 2026 method.

Only team "Pre-Approvals IP Offshore", Employee records, from June 2026 onward.
Earlier months keep their stored scores and are refused if requested. Each
stored record is scored from its own raw counts in ``record_payload.raw_data``.

Modes:

* Dry run (default): reads only and writes nothing. Writes a before/after CSV
  to ``--report``.
* ``--apply --backup PATH``: writes a complete JSON backup of every row it will
  touch first (refuses to overwrite an existing backup), then updates score,
  grade, status, KPI values and the payload's evaluation, KPI and derived raw
  fields in ONE transaction. Idempotent: a second run changes nothing.
* ``--restore PATH``: puts back exactly the rows in a backup, in one
  transaction, and verifies every restored row against the backup.

Refused, never touched: any record whose team, level and month has an approved
monthly configuration version or an active evaluation revision. Records whose
``PolicyRej`` count is missing are reported and left unchanged unless
``--treat-missing-policy-as-zero`` is given.

Caches are cleared after apply and restore, as the upload path does.
Not run automatically. Not wired into startup or migrations.

Usage (from ``Backend/``)::

    python -m scripts.rescore_preapprovals_offshore --report out/dry_run.csv
    python -m scripts.rescore_preapprovals_offshore --months June July --report out/dry_run.csv
    python -m scripts.rescore_preapprovals_offshore --apply --backup out/backup.json --report out/applied.csv
    python -m scripts.rescore_preapprovals_offshore --restore out/backup.json
    python -m scripts.rescore_preapprovals_offshore --database-url URL --report out/dry_run.csv
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import or_  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from config.loader import load_team_config  # noqa: E402
from models.models import (  # noqa: E402
    Employee,
    EvaluationRevision,
    KPIValue,
    PerformanceRecord,
    Team,
    TeamConfigurationVersion,
)
from services.preapprovals_offshore_scoring import (  # noqa: E402
    EFFECTIVE_MONTH,
    EFFECTIVE_PERIOD_TEXT,
    EFFECTIVE_YEAR,
    NEW_METHOD_ID,
    POLICY_INDICATOR_KEY,
    RAW_COUNT_COLUMNS,
    TEAM_NAME,
    OffshoreDataError,
    OffshoreScore,
    config_grade_thresholds,
    config_kpi_meta,
    counts_from_mapping,
    derived_raw_values,
    kpi_values,
    month_number,
    score_counts,
)
from utils.performance_status import status_for_grade  # noqa: E402

BACKUP_FORMAT = "preapprovals_offshore_rescore_backup"
BACKUP_VERSION = 1
EMPLOYEE_LEVEL = "Employee"
MONTH_NAMES = {number: name for number, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    start=1,
)}
KPI_ORDER = ("Rejection", "InitialError", "Submission", POLICY_INDICATOR_KEY)
REPORT_LABELS = {
    "Rejection": "rejection",
    "InitialError": "initial_error",
    "Submission": "submission",
    POLICY_INDICATOR_KEY: "policy_rejection",
}
REPORT_FIELDS = ("actual", "target", "achievement", "weight")
REPORT_COLUMNS = (
    ["employee_id", "year", "month", "performance_level", "position_name", "status", "reason", "flags"]
    + [f"{count}" for count in (
        "assigned_requests", "approved_requests", "rejected_requests", "policy_rejected",
        "approved_within_48h", "submitted_claims", "error_claims",
    )]
    + [f"{when}_{label}_{field}" for label in REPORT_LABELS.values() for when in ("old", "new") for field in REPORT_FIELDS]
    + ["old_score", "new_score", "old_grade", "new_grade"]
)
COUNT_REPORT_COLUMNS = {
    "AssignedRequest": "assigned_requests",
    "ApprovedRequests": "approved_requests",
    "RejectedRequests": "rejected_requests",
    "PolicyRej": "policy_rejected",
    "ApprovalWithin48HR": "approved_within_48h",
    "SubmittedClaims": "submitted_claims",
    "ErrosClaims": "error_claims",
}
VALUE_TOLERANCE = 1e-4

STATUS_RESCORED = "rescored"
STATUS_UNCHANGED = "unchanged"
STATUS_SKIPPED = "skipped"
STATUS_REFUSED = "refused"


class EligibilityError(ValueError):
    """A requested month is before the effective period, or otherwise not allowed."""


class RestoreVerificationError(RuntimeError):
    """A restored row does not match the backup."""


@dataclass
class PlanRow:
    record: PerformanceRecord
    month_no: int | None
    status: str
    reason: str = ""
    flags: list[str] = field(default_factory=list)
    counts: dict[str, float] = field(default_factory=dict)
    result: OffshoreScore | None = None
    new_kpis: list[dict[str, Any]] = field(default_factory=list)
    old_kpis: dict[str, KPIValue] = field(default_factory=dict)
    new_payload: dict[str, Any] | None = None
    new_grade: str | None = None
    new_status: str | None = None


# ---------------------------------------------------------------- selection

def parse_months(values: list[str] | None, year: int) -> list[int] | None:
    """Turn '--months' values into month numbers. Earlier months are refused."""
    if not values:
        return None
    numbers: list[int] = []
    for value in values:
        number = month_number(value)
        if number is None:
            raise EligibilityError(f"'{value}' is not a month name or a month number (1-12)")
        numbers.append(number)
    if year < EFFECTIVE_YEAR or (year == EFFECTIVE_YEAR and min(numbers) < EFFECTIVE_MONTH):
        early = sorted({MONTH_NAMES[number] for number in numbers if (year, number) < (EFFECTIVE_YEAR, EFFECTIVE_MONTH)})
        raise EligibilityError(
            f"Refused: {', '.join(early)} {year} is before the effective period {EFFECTIVE_PERIOD_TEXT}. "
            "Those months keep the old method and their stored scores; they are not rescored."
        )
    return sorted(set(numbers))


def team_ids_for_offshore(db: Session) -> list:
    rows = db.query(Team.id).filter(or_(Team.name == TEAM_NAME, Team.db_name == TEAM_NAME)).all()
    return [row[0] for row in rows]


def locked_months(db: Session, team_ids: list, year: int) -> set[tuple[str, int]]:
    """(performance level, month) pairs with an approved monthly version or an active revision."""
    locked: set[tuple[str, int]] = set()
    if not team_ids:
        return locked
    approved = (
        db.query(TeamConfigurationVersion.performance_level, TeamConfigurationVersion.effective_from_month)
        .filter(
            TeamConfigurationVersion.team_id.in_(team_ids),
            TeamConfigurationVersion.status == "approved",
            TeamConfigurationVersion.performance_level.isnot(None),
            TeamConfigurationVersion.effective_from_year == year,
        )
        .all()
    )
    locked.update((str(level), int(month)) for level, month in approved)
    revisions = (
        db.query(EvaluationRevision.performance_level, EvaluationRevision.month)
        .filter(
            EvaluationRevision.team_id.in_(team_ids),
            EvaluationRevision.status == "active",
            EvaluationRevision.year == year,
        )
        .all()
    )
    locked.update((str(level), int(month)) for level, month in revisions)
    return locked


def load_records(db: Session, team_ids: list, year: int) -> list[PerformanceRecord]:
    if not team_ids:
        return []
    return (
        db.query(PerformanceRecord)
        .filter(PerformanceRecord.team_id.in_(team_ids), PerformanceRecord.year == year)
        .order_by(PerformanceRecord.month, PerformanceRecord.id)
        .all()
    )


def load_kpis(db: Session, record_ids: list, year: int) -> dict[Any, list[KPIValue]]:
    grouped: dict[Any, list[KPIValue]] = {}
    if not record_ids:
        return grouped
    for row in db.query(KPIValue).filter(KPIValue.record_id.in_(record_ids), KPIValue.record_year == year).all():
        grouped.setdefault(row.record_id, []).append(row)
    return grouped


def default_months(year: int, records: list[PerformanceRecord]) -> list[int]:
    """Every stored month of the year from the effective period onward."""
    numbers = {month_number(record.month) for record in records}
    return sorted(number for number in numbers if number and (year, number) >= (EFFECTIVE_YEAR, EFFECTIVE_MONTH))


# ---------------------------------------------------------------- planning

def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _strip_flags(kpi: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in kpi.items() if key not in ("applicable", "tracking_only")}


def _updated_payload(payload: Any, result: OffshoreScore, grade: str, new_kpis: list[dict[str, Any]]) -> dict[str, Any]:
    updated = copy.deepcopy(payload) if isinstance(payload, dict) else {}
    raw = updated.get("raw_data")
    if isinstance(raw, dict):
        raw.update(derived_raw_values(result))  # adds derived keys only
    evaluation = updated.get("evaluation")
    if isinstance(evaluation, dict):
        evaluation["score"] = result.score
        evaluation["grade"] = grade
    updated["kpi_values"] = [_strip_flags(kpi) for kpi in new_kpis]
    return updated


def _old_kpi_row_matches(old: KPIValue, new: dict[str, Any]) -> bool:
    pairs = (
        (old.actual_value, new["actual_value"]),
        (old.target_value, new["target_value"]),
        (old.achievement_ratio, new["achievement_ratio"]),
        (old.weight_applied, new["weight_applied"]),
        (old.contribution, new["contribution"]),
    )
    for stored, computed in pairs:
        stored_number = _decimal(stored)
        if stored_number is None or abs(float(stored_number) - float(computed)) > VALUE_TOLERANCE:
            return False
    return True


def plan_records(db: Session, records: list[PerformanceRecord], kpis_by_record: dict[Any, list[KPIValue]],
                 year: int, months: list[int] | None, treat_missing_policy: bool) -> list[PlanRow]:
    team_ids = {record.team_id for record in records}
    locked = locked_months(db, list(team_ids), year)
    config = load_team_config(TEAM_NAME)
    thresholds = config_grade_thresholds(config)
    meta = config_kpi_meta(config)
    selected = set(months) if months is not None else None

    plans: list[PlanRow] = []
    for record in records:
        month_no = month_number(record.month)
        if month_no is None or (year, month_no) < (EFFECTIVE_YEAR, EFFECTIVE_MONTH):
            continue  # before the effective period, or not a month: not in scope of this run
        if selected is not None and month_no not in selected:
            continue
        plan = PlanRow(record=record, month_no=month_no, status=STATUS_SKIPPED)
        plan.old_kpis = {row.kpi_key: row for row in kpis_by_record.get(record.id, [])}
        level = str(record.performance_level or "")
        if (level, month_no) in locked:
            plan.status = STATUS_REFUSED
            plan.reason = "month has an approved monthly evaluation version or an active evaluation revision"
            plans.append(plan)
            continue
        if level != EMPLOYEE_LEVEL:
            plan.reason = f"performance level '{level}' is not scored by this method"
            plans.append(plan)
            continue
        payload = record.record_payload if isinstance(record.record_payload, dict) else None
        raw = payload.get("raw_data") if payload else None
        if not isinstance(raw, dict):
            plan.reason = "no raw_data in the stored payload"
            plans.append(plan)
            continue
        scoring_raw = dict(raw)
        if _blank(scoring_raw.get("PolicyRej")):
            if not treat_missing_policy:
                plan.reason = "PolicyRej is missing; not rescored (leave unchanged, or pass --treat-missing-policy-as-zero)"
                plans.append(plan)
                continue
            scoring_raw["PolicyRej"] = 0
            plan.flags.append("PolicyRej missing: scored as 0 (--treat-missing-policy-as-zero)")
        try:
            counts = counts_from_mapping(scoring_raw)
        except OffshoreDataError as error:
            plan.reason = f"cannot be rescored: {error}"
            plans.append(plan)
            continue
        plan.counts = {COUNT_REPORT_COLUMNS[column]: float(getattr(counts, attr)) for column, attr in (
            ("AssignedRequest", "assigned"), ("ApprovedRequests", "approved"), ("RejectedRequests", "rejected"),
            ("PolicyRej", "policy_rejected"), ("ApprovalWithin48HR", "approved_within_48h"),
            ("SubmittedClaims", "submitted"), ("ErrosClaims", "errors"),
        )}
        result = score_counts(counts, thresholds)
        new_kpis = kpi_values(result, meta)
        plan.result = result
        plan.new_kpis = new_kpis
        plan.new_grade = result.grade
        plan.new_status = status_for_grade(result.grade)
        plan.new_payload = _updated_payload(payload, result, result.grade, new_kpis)

        unchanged = (
            _decimal(record.score) is not None
            and abs(float(_decimal(record.score)) - result.score) < VALUE_TOLERANCE
            and record.grade == result.grade
            and record.status == plan.new_status
            and record.record_payload == plan.new_payload
            and all(
                kpi["kpi_key"] in plan.old_kpis and _old_kpi_row_matches(plan.old_kpis[kpi["kpi_key"]], kpi)
                for kpi in new_kpis
            )
            and len(plan.old_kpis) == len(new_kpis)
        )
        if unchanged:
            plan.status = STATUS_UNCHANGED
            plan.reason = "already scored by this method"
        else:
            plan.status = STATUS_RESCORED
            plan.reason = "rescored by the June 2026 method"
        plans.append(plan)
    return plans


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return value != value  # NaN
    except Exception:
        return False


# ---------------------------------------------------------------- report

def _fmt(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return float(value)
    return value


def report_rows(plans: list[PlanRow], employee_codes: dict[Any, str]) -> list[dict[str, Any]]:
    rows = []
    for plan in plans:
        record = plan.record
        row: dict[str, Any] = {
            "employee_id": employee_codes.get(record.employee_id, str(record.employee_id)),
            "year": record.year,
            "month": record.month,
            "performance_level": record.performance_level,
            "position_name": record.position_name or "",
            "status": plan.status,
            "reason": plan.reason,
            "flags": "; ".join(plan.flags),
            "old_score": _fmt(record.score),
            "old_grade": record.grade,
            "new_score": plan.result.score if plan.result else "",
            "new_grade": plan.new_grade or "",
        }
        for column, key in COUNT_REPORT_COLUMNS.items():
            row[key] = _fmt(plan.counts.get(key))
        new_by_key = {kpi["kpi_key"]: kpi for kpi in plan.new_kpis}
        for kpi_key, label in REPORT_LABELS.items():
            old = plan.old_kpis.get(kpi_key)
            new = new_by_key.get(kpi_key)
            for field_name, old_attr, new_attr in (
                ("actual", "actual_value", "actual_value"),
                ("target", "target_value", "target_value"),
                ("achievement", "achievement_ratio", "achievement_ratio"),
                ("weight", "weight_applied", "weight_applied"),
            ):
                row[f"old_{label}_{field_name}"] = _fmt(getattr(old, old_attr, None)) if old is not None else ""
                row[f"new_{label}_{field_name}"] = new[new_attr] if new is not None else ""
        rows.append({column: row.get(column, "") for column in REPORT_COLUMNS})
    return rows


def write_report(path: Path, plans: list[PlanRow], employee_codes: dict[Any, str]) -> int:
    rows = report_rows(plans, employee_codes)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


# ---------------------------------------------------------------- backup

def _kpi_snapshot(row: KPIValue) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "record_id": str(row.record_id),
        "record_year": int(row.record_year),
        "kpi_key": row.kpi_key,
        "actual_value": str(row.actual_value),
        "target_value": str(row.target_value),
        "achievement_ratio": str(row.achievement_ratio),
        "weight_applied": str(row.weight_applied),
        "contribution": str(row.contribution),
    }


def _record_snapshot(record: PerformanceRecord, kpis: list[KPIValue]) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "year": int(record.year),
        "employee_id": str(record.employee_id),
        "team_id": str(record.team_id),
        "month": record.month,
        "performance_level": record.performance_level,
        "score": str(record.score),
        "grade": record.grade,
        "status": record.status,
        "record_payload": copy.deepcopy(record.record_payload),
        "kpi_values": [_kpi_snapshot(row) for row in sorted(kpis, key=lambda item: str(item.id))],
    }


def write_backup(path: Path, year: int, plans: list[PlanRow], kpis_by_record: dict[Any, list[KPIValue]]) -> int:
    if path.exists():
        raise FileExistsError(f"Refused: backup {path} already exists. Choose a new path so no backup is overwritten.")
    touched = [plan for plan in plans if plan.status == STATUS_RESCORED]
    document = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "team": TEAM_NAME,
        "year": year,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "records": [_record_snapshot(plan.record, kpis_by_record.get(plan.record.id, [])) for plan in touched],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, default=str)
    return len(touched)


def load_backup(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("format") != BACKUP_FORMAT or document.get("version") != BACKUP_VERSION:
        raise ValueError(f"{path} is not a {BACKUP_FORMAT} v{BACKUP_VERSION} backup")
    return document


# ---------------------------------------------------------------- apply / restore

def apply_plans(db: Session, plans: list[PlanRow], year: int) -> dict[str, int]:
    applied = {"records": 0, "kpi_updated": 0, "kpi_inserted": 0}
    for plan in plans:
        if plan.status != STATUS_RESCORED:
            continue
        record = plan.record
        record.score = round(plan.result.score, 2)
        record.grade = plan.new_grade
        record.status = plan.new_status
        record.record_payload = plan.new_payload
        existing = dict(plan.old_kpis)
        for kpi in plan.new_kpis:
            row = existing.get(kpi["kpi_key"])
            if row is None:
                db.add(KPIValue(
                    record_id=record.id,
                    record_year=year,
                    kpi_key=kpi["kpi_key"],
                    actual_value=kpi["actual_value"],
                    target_value=kpi["target_value"],
                    achievement_ratio=kpi["achievement_ratio"],
                    weight_applied=kpi["weight_applied"],
                    contribution=kpi["contribution"],
                ))
                applied["kpi_inserted"] += 1
                continue
            row.actual_value = kpi["actual_value"]
            row.target_value = kpi["target_value"]
            row.achievement_ratio = kpi["achievement_ratio"]
            row.weight_applied = kpi["weight_applied"]
            row.contribution = kpi["contribution"]
            applied["kpi_updated"] += 1
        applied["records"] += 1
    db.flush()
    return applied


def restore_backup(db: Session, document: dict[str, Any]) -> dict[str, int]:
    year = int(document["year"])
    restored = {"records": 0, "kpi_rows": 0, "kpi_removed": 0}
    for snapshot in document["records"]:
        record = (
            db.query(PerformanceRecord)
            .filter(PerformanceRecord.id == _uuid(snapshot["id"]), PerformanceRecord.year == int(snapshot["year"]))
            .one()
        )
        record.score = Decimal(snapshot["score"])
        record.grade = snapshot["grade"]
        record.status = snapshot["status"]
        record.record_payload = copy.deepcopy(snapshot["record_payload"])
        backup_ids = {item["id"] for item in snapshot["kpi_values"]}
        stale = (
            db.query(KPIValue)
            .filter(KPIValue.record_id == record.id, KPIValue.record_year == int(snapshot["year"]))
            .all()
        )
        for row in stale:
            if str(row.id) not in backup_ids:
                db.delete(row)
                restored["kpi_removed"] += 1
        for item in snapshot["kpi_values"]:
            row = db.query(KPIValue).filter(KPIValue.id == _uuid(item["id"])).one_or_none()
            if row is None:
                row = KPIValue(id=_uuid(item["id"]))
                db.add(row)
            row.record_id = _uuid(item["record_id"])
            row.record_year = int(item["record_year"])
            row.kpi_key = item["kpi_key"]
            row.actual_value = Decimal(item["actual_value"])
            row.target_value = Decimal(item["target_value"])
            row.achievement_ratio = Decimal(item["achievement_ratio"])
            row.weight_applied = Decimal(item["weight_applied"])
            row.contribution = Decimal(item["contribution"])
            restored["kpi_rows"] += 1
        restored["records"] += 1
    db.flush()
    verify_restore(db, document)
    return restored


def verify_restore(db: Session, document: dict[str, Any]) -> None:
    for snapshot in document["records"]:
        record = (
            db.query(PerformanceRecord)
            .filter(PerformanceRecord.id == _uuid(snapshot["id"]), PerformanceRecord.year == int(snapshot["year"]))
            .one()
        )
        if _decimal(record.score) != _decimal(snapshot["score"]) or record.grade != snapshot["grade"] or record.status != snapshot["status"]:
            raise RestoreVerificationError("a restored record does not match the backup")
        if record.record_payload != snapshot["record_payload"]:
            raise RestoreVerificationError("a restored record payload does not match the backup")
        current = (
            db.query(KPIValue)
            .filter(KPIValue.record_id == record.id, KPIValue.record_year == int(snapshot["year"]))
            .all()
        )
        if sorted(str(row.id) for row in current) != sorted(item["id"] for item in snapshot["kpi_values"]):
            raise RestoreVerificationError("a record's KPI rows do not match the backup")
        by_id = {str(row.id): row for row in current}
        for item in snapshot["kpi_values"]:
            row = by_id[item["id"]]
            for attr in ("kpi_key", "actual_value", "target_value", "achievement_ratio", "weight_applied", "contribution"):
                stored = row.kpi_key if attr == "kpi_key" else _decimal(getattr(row, attr))
                expected = item[attr] if attr == "kpi_key" else _decimal(item[attr])
                if stored != expected:
                    raise RestoreVerificationError(f"a restored KPI row ({attr}) does not match the backup")


def _uuid(value: str):
    import uuid

    return uuid.UUID(str(value))


def flush_caches() -> str:
    """Clear the caches the upload path clears. Returns a note for the operator."""
    try:
        from api.dependencies import clear_serialization_cache
        from services.cache_invalidation_service import CacheInvalidationService

        CacheInvalidationService.flush_all()
        clear_serialization_cache()
        return "caches cleared (flush_all and serialization cache)"
    except Exception as error:  # noqa: BLE001 - reported to the operator, not swallowed
        return f"caches not cleared ({error}); restart the server before reading results"


# ---------------------------------------------------------------- CLI

def _redacted(url: str) -> str:
    if url.startswith("sqlite"):
        return url
    scheme, _, rest = url.partition("://")
    return f"{scheme}://***@{rest.rpartition('@')[2]}" if "@" in rest else f"{scheme}://{rest}"


def _summary(plans: list[PlanRow]) -> dict[str, int]:
    counts = {STATUS_RESCORED: 0, STATUS_UNCHANGED: 0, STATUS_SKIPPED: 0, STATUS_REFUSED: 0}
    for plan in plans:
        counts[plan.status] = counts.get(plan.status, 0) + 1
    return counts


def run(db: Session, *, year: int, months: list[int] | None, apply: bool, report: Path | None,
        backup: Path | None, treat_missing_policy: bool) -> dict[str, Any]:
    team_ids = team_ids_for_offshore(db)
    records = load_records(db, team_ids, year)
    if months is None:
        months = default_months(year, records)
    kpis = load_kpis(db, [record.id for record in records], year)
    plans = plan_records(db, records, kpis, year, months, treat_missing_policy)
    employee_ids = {record.employee_id for record in records}
    employee_codes = {
        row_id: str(code)
        for row_id, code in db.query(Employee.id, Employee.employee_id).filter(Employee.id.in_(employee_ids)).all()
    } if employee_ids else {}
    summary = {"team_rows": len(team_ids), "records_seen": len(records), "counts": _summary(plans)}
    if report is not None:
        summary["report_rows"] = write_report(report, plans, employee_codes)
    if apply:
        if backup is None:
            raise ValueError("--apply requires --backup PATH")
        summary["backup_records"] = write_backup(backup, year, plans, kpis)
        summary["applied"] = apply_plans(db, plans, year)
    return summary


def restore(db: Session, path: Path) -> dict[str, Any]:
    document = load_backup(path)
    for snapshot in document["records"]:
        if (int(snapshot["year"]), month_number(snapshot["month"]) or 0) < (EFFECTIVE_YEAR, EFFECTIVE_MONTH):
            raise EligibilityError(f"Refused: backup contains a month before {EFFECTIVE_PERIOD_TEXT}")
    return {"restored": restore_backup(db, document)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, default=EFFECTIVE_YEAR, help="reporting year (default 2026)")
    parser.add_argument("--months", nargs="+", help="month names or numbers; default: every stored month from June 2026")
    parser.add_argument("--report", type=Path, help="write the before/after CSV report here")
    parser.add_argument("--apply", action="store_true", help="write the changes (requires --backup)")
    parser.add_argument("--backup", type=Path, help="JSON backup path, written before --apply changes anything")
    parser.add_argument("--restore", type=Path, help="restore the rows in a backup file")
    parser.add_argument("--treat-missing-policy-as-zero", action="store_true",
                        help="score records without PolicyRej as 0 (default: leave them unchanged and report them)")
    parser.add_argument("--database-url", help="explicit database URL (default: the app's configured DATABASE_URL)")
    args = parser.parse_args(argv)

    if args.restore and (args.apply or args.backup or args.report):
        parser.error("--restore cannot be combined with --apply, --backup or --report")
    if args.apply and not args.backup:
        parser.error("--apply requires --backup PATH")
    if not args.restore and args.report is None:
        parser.error("--report PATH is required for a dry run or an apply")

    try:
        if args.year < EFFECTIVE_YEAR:
            raise EligibilityError(
                f"Refused: year {args.year} is before the effective period {EFFECTIVE_PERIOD_TEXT}. "
                "Those months keep the old method and their stored scores."
            )
        months = parse_months(args.months, args.year)
    except EligibilityError as error:
        print(str(error))
        return 2

    if args.database_url:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(args.database_url)
        session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        target = _redacted(args.database_url)
    else:
        from config.database import SessionLocal, engine

        session_factory = SessionLocal
        target = _redacted(str(engine.url))

    print(f"Database: {target}")
    with session_factory() as db:
        try:
            if args.restore:
                result = restore(db, args.restore)
                db.commit()
                print(f"Restored: {result['restored']}")
                print(flush_caches())
                return 0
            result = run(
                db,
                year=args.year,
                months=months,
                apply=args.apply,
                report=args.report,
                backup=args.backup,
                treat_missing_policy=args.treat_missing_policy_as_zero,
            )
            if args.apply:
                db.commit()
            else:
                db.rollback()
        except EligibilityError as error:
            db.rollback()
            print(str(error))
            return 2
        except RestoreVerificationError as error:
            db.rollback()
            print(f"Restore stopped and rolled back: {error}")
            return 1
        except Exception:
            db.rollback()
            raise

    mode = "APPLIED" if args.apply else "DRY RUN (nothing written)"
    print(f"{mode}: team={TEAM_NAME} year={args.year}")
    print(f"Records in year: {result['records_seen']}; team rows: {result['team_rows']}")
    for status, count in result["counts"].items():
        print(f"  {status}: {count}")
    if "report_rows" in result:
        print(f"Report: {args.report} ({result['report_rows']} rows)")
    if args.apply:
        print(f"Backup: {args.backup} ({result['backup_records']} records)")
        print(f"Applied: {result['applied']}")
        print(flush_caches())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
