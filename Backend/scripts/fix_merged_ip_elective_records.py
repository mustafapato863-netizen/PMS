"""Re-score Pre-Approvals IP Elective Dubai records that merged other KPI rows.

Before the upload fix (``services/upload_record_collisions.py``) an employee
who appeared twice for one month in a multi-sheet upload - on the IP Final
Dubai *and* IP Elective Dubai sheets, or on both IP Elective workstream tables
- was saved as ONE record (team = the last sheet) carrying every duplicate's
KPI rows. The stored score was their unscaled sum (production check
2026-10-06: 16 records, grade E, scores 1.51-2.72; one May record would have
reached 171.77 from both Elective workstreams).

For each IP Elective Dubai record this script keeps the KPI rows of the
record's own position (``position_name``, e.g. ``ER / IP Approval``) as the
only scoring rows and re-scores them exactly like a normal record (0-100,
contributions capped, team grade thresholds). Every other KPI row (IP Final
Dubai ``combined_*`` / ``ip_approval_*`` / ``ip_discharge_*`` or the other
workstream's keys) is removed from ``kpi_values`` - so it can never reach a
score, grade, driver, KPI filter or insight - and preserved verbatim in
``record_payload.reference_kpi_values`` with ``"scoring": false``, its source
team and the reason.

Safety:

* Dry run by default: prints what would change and writes nothing.
* ``--apply`` writes inside one transaction (rolled back on any error).
* Idempotent: once a record holds only its position's KPI rows it is left
  alone, so a second run changes nothing.
* Records whose position is missing/unknown are reported, never modified.
* No schema change; no Alembic migration.

Usage (from ``Backend/``)::

    python -m scripts.fix_merged_ip_elective_records                       # dry run
    python -m scripts.fix_merged_ip_elective_records --apply               # write
    python -m scripts.fix_merged_ip_elective_records --database-url URL    # explicit DB
"""

from __future__ import annotations

import argparse
import copy
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, or_  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from config.loader import load_team_config  # noqa: E402
from data_cleaning.standard_mappings import calculate_grade  # noqa: E402
from models.models import Employee, KPIValue, PerformanceRecord, Team  # noqa: E402
from services.seeding_service import DatabaseSeeder  # noqa: E402
from utils.performance_status import GRADE_STATUSES, status_for_grade  # noqa: E402

ELECTIVE_TEAM = "Pre-Approvals IP Elective Dubai"
FINAL_DUBAI_TEAM = "Pre-Approvals IP Final Dubai"
REASON = (
    "Merged from a duplicate employee-month row in the same upload; kept for reference only. "
    "Not part of the score, grade, drivers or insights."
)


def _position_keys(config: dict[str, Any]) -> dict[str, set[str]]:
    positions = (((config.get("performance_levels") or {}).get("Employee") or {}).get("positions") or {})
    return {
        str(name).strip().casefold(): {str(kpi["key"]) for kpi in (value.get("kpis") or []) if kpi.get("key")}
        for name, value in positions.items()
    }


def _all_keys(config: dict[str, Any]) -> set[str]:
    return set().union(*_position_keys(config).values()) if _position_keys(config) else set()


def _status(grade: str) -> str:
    return status_for_grade(grade)


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def _reference_row(value: KPIValue, *, source_team: str) -> dict[str, Any]:
    return {
        "kpi_key": value.kpi_key,
        "actual_value": _num(value.actual_value),
        "target_value": _num(value.target_value),
        "achievement_ratio": _num(value.achievement_ratio),
        "weight_applied": _num(value.weight_applied),
        "contribution": _num(value.contribution),
        "scoring": False,
        "source_team": source_team,
        "reason": REASON,
    }


def _patched_payload(payload: Any, *, moved: list[dict[str, Any]], score: float, grade: str, status: str | None) -> Any:
    if not isinstance(payload, dict):
        payload = {}
    updated = copy.deepcopy(payload)
    moved_keys = {row["kpi_key"] for row in moved}
    if isinstance(updated.get("kpi_values"), list):
        updated["kpi_values"] = [
            value for value in updated["kpi_values"]
            if not (isinstance(value, dict) and value.get("kpi_key") in moved_keys)
        ]
    existing = [row for row in (updated.get("reference_kpi_values") or []) if row.get("kpi_key") not in moved_keys]
    updated["reference_kpi_values"] = existing + moved
    evaluation = updated.get("evaluation")
    if isinstance(evaluation, dict):
        evaluation["score"] = score
        evaluation["grade"] = grade
    if status is not None and "status" in updated:
        updated["status"] = status
    return updated


def run(db: Session, *, apply: bool = False) -> dict[str, Any]:
    """Plan (and with ``apply`` write) the correction. Returns a report dict."""
    elective = load_team_config(ELECTIVE_TEAM)
    positions = _position_keys(elective)
    elective_keys = _all_keys(elective)
    final_keys = _all_keys(load_team_config(FINAL_DUBAI_TEAM))
    thresholds = elective.get("grade_thresholds")
    report: dict[str, Any] = {
        "apply": apply,
        "records_checked": 0,
        "records_to_fix": 0,
        "already_clean": 0,
        "skipped_unknown_position": 0,
        "grade_changes": 0,
        "changes": [],
        "skipped": [],
    }
    team_ids = [
        team.id
        for team in db.query(Team).filter(
            or_(func.lower(Team.name) == ELECTIVE_TEAM.casefold(), func.lower(Team.db_name) == ELECTIVE_TEAM.casefold())
        ).all()
    ]
    if not team_ids:
        return report

    records = (
        db.query(PerformanceRecord, Employee.employee_id)
        .join(Employee, Employee.id == PerformanceRecord.employee_id)
        .filter(PerformanceRecord.team_id.in_(team_ids))
        .order_by(PerformanceRecord.year, PerformanceRecord.month, Employee.employee_id)
        .all()
    )
    for record, employee_code in records:
        report["records_checked"] += 1
        values = (
            db.query(KPIValue)
            .filter(KPIValue.record_id == record.id, KPIValue.record_year == record.year)
            .order_by(KPIValue.kpi_key)
            .all()
        )
        position = str(record.position_name or "").strip()
        scoring_keys = positions.get(position.casefold())
        if scoring_keys is None:
            record_keys = {value.kpi_key for value in values}
            touched = [keys for keys in positions.values() if keys & record_keys]
            if (record_keys - elective_keys) or len(touched) > 1:
                report["skipped_unknown_position"] += 1
                report["skipped"].append({
                    "employee_id": employee_code, "month": record.month, "year": record.year,
                    "position": position or None, "kpi_keys": [value.kpi_key for value in values],
                })
            else:
                report["already_clean"] += 1
            continue

        scoring = [value for value in values if value.kpi_key in scoring_keys]
        extra = [value for value in values if value.kpi_key not in scoring_keys]
        if not extra:
            report["already_clean"] += 1
            continue

        new_score = DatabaseSeeder._score_from_kpi_rows(scoring)
        new_grade = calculate_grade(new_score, thresholds)
        new_status = _status(new_grade) if (record.status in GRADE_STATUSES or not record.status) else None
        moved = [
            _reference_row(value, source_team=FINAL_DUBAI_TEAM if value.kpi_key in final_keys else f"{ELECTIVE_TEAM} (other workstream)")
            for value in extra
        ]
        old_score = float(record.score)
        report["records_to_fix"] += 1
        if record.grade != new_grade:
            report["grade_changes"] += 1
        report["changes"].append({
            "record_id": str(record.id),
            "employee_id": employee_code,
            "month": record.month,
            "year": record.year,
            "team": ELECTIVE_TEAM,
            "position": position,
            "score": [old_score, new_score],
            "grade": [record.grade, new_grade],
            "status": [record.status, new_status if new_status is not None else record.status],
            "scoring_keys": [value.kpi_key for value in scoring],
            "missing_scoring_keys": sorted(scoring_keys - {value.kpi_key for value in scoring}),
            "reference_keys": [row["kpi_key"] for row in moved],
        })
        if apply:
            for value in extra:
                db.delete(value)
            record.score = new_score
            record.grade = new_grade
            if new_status is not None:
                record.status = new_status
            record.record_payload = _patched_payload(
                record.record_payload, moved=moved, score=new_score, grade=new_grade, status=new_status,
            )

    if apply:
        db.flush()
    return report


def _print_report(report: dict[str, Any], *, target: str = "") -> None:
    mode = "APPLY" if report["apply"] else "DRY RUN (nothing written)"
    print(f"Merged IP Elective Dubai records fix - {mode}" + (f" - target: {target}" if target else ""))
    if report["changes"]:
        print("  employee_id | month year | team | position | before score/grade/status -> after score/grade/status | non-scoring reference rows")
    for change in report["changes"]:
        missing = f" (missing scoring keys: {', '.join(change['missing_scoring_keys'])})" if change["missing_scoring_keys"] else ""
        print(
            f"  {change['employee_id']} | {change['month']} {change['year']} | {change['team']} | {change['position']} | "
            f"{change['score'][0]:.2f} {change['grade'][0]} {change['status'][0]} -> "
            f"{change['score'][1]:.2f} {change['grade'][1]} {change['status'][1]} | "
            f"{', '.join(change['reference_keys'])}{missing}"
        )
    for row in report["skipped"]:
        print(f"  SKIPPED (unknown position, left unchanged, review manually): {row}")
    print("  Summary:")
    for key in ("records_checked", "records_to_fix", "grade_changes", "already_clean", "skipped_unknown_position"):
        print(f"    {key}: {report[key]}")
    by_month = Counter(f"{change['month']} {change['year']}" for change in report["changes"])
    if by_month:
        print("    records_to_fix by month: " + ", ".join(f"{month}={count}" for month, count in sorted(by_month.items())))
        moves = Counter(f"{change['grade'][0]}->{change['grade'][1]}" for change in report["changes"])
        print("    grade moves: " + ", ".join(f"{move}={count}" for move, count in sorted(moves.items())))
        before = [change["score"][0] for change in report["changes"]]
        after = [change["score"][1] for change in report["changes"]]
        print(f"    score range before: {min(before):.2f}-{max(before):.2f}; after: {min(after):.2f}-{max(after):.2f}")


def _redacted(url: str) -> str:
    if url.startswith("sqlite"):
        return url
    scheme, _, rest = url.partition("://")
    return f"{scheme}://***@{rest.rpartition('@')[2]}" if "@" in rest else f"{scheme}://{rest}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    parser.add_argument("--database-url", help="explicit database URL (default: the app's configured DATABASE_URL)")
    args = parser.parse_args(argv)

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

    with session_factory() as db:
        try:
            report = run(db, apply=args.apply)
            if args.apply:
                db.commit()
            else:
                db.rollback()
        except Exception:
            db.rollback()
            raise
    _print_report(report, target=target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
