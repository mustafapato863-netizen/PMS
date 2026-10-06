"""Re-score Marketing ``cw_error_free`` rows saved under the old lower_better rule.

``cw_error_free`` ("Error-free content ratio") is higher-is-better. Until the
config fix it was configured ``lower_better``, so Marketing imports stored an
inverted achievement/contribution for it, and therefore an inflated or
deflated record score/grade. Pages that read through ``DashboardRecordService``
already correct this at read time; this script rewrites the stored values so
SQL aggregates (average/min/max score, grade filters) agree as well.

Safety:

* Dry run by default: prints what would change and writes nothing.
* ``--apply`` writes inside one transaction (rolled back on any error).
* Idempotent: a row is only changed when its stored contribution still equals
  the old lower_better score; already-corrected rows are left alone, and rows
  matching neither rule are reported as ``unexpected`` (never modified).
* No schema change; no Alembic migration.

Usage (from ``Backend/``)::

    python -m scripts.fix_cw_error_free_direction            # dry run
    python -m scripts.fix_cw_error_free_direction --apply    # write
"""

from __future__ import annotations

import argparse
import copy
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.orm import Session  # noqa: E402

from config.loader import load_team_config  # noqa: E402
from data_cleaning.standard_mappings import calculate_grade  # noqa: E402
from models.models import KPIValue, PerformanceRecord, Team, TeamKPIConfig  # noqa: E402

KPI_KEY = "cw_error_free"
TEAM_NAME = "Marketing"
OLD_DIRECTION = "lower_better"
NEW_DIRECTION = "higher_better"
# KPIValue.contribution is Numeric(7, 4).
TOLERANCE = Decimal("0.0005")


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _effective(actual: Decimal, target: Decimal, direction: str) -> Decimal:
    """Exactly the Marketing import formula (``marketing_import_service``)."""
    if direction == "lower_better":
        achievement = Decimal("1") if actual == 0 else target / actual
    else:
        achievement = Decimal("0") if target == 0 else actual / target
    return max(Decimal("0"), min(achievement, Decimal("1")))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _status(grade: str) -> str:
    if grade == "A":
        return "Exceeds"
    if grade in {"B", "C"}:
        return "Meets"
    return "Below"


def _patched_payload(payload: Any, *, ratio: float, contribution: float, score: float, grade: str, status: str) -> Any:
    if not isinstance(payload, dict):
        return payload
    updated = copy.deepcopy(payload)
    for value in updated.get("kpi_values") or []:
        if isinstance(value, dict) and value.get("kpi_key") == KPI_KEY:
            value["direction"] = NEW_DIRECTION
            value["achievement_ratio"] = ratio
            value["contribution"] = contribution
    evaluation = updated.get("evaluation")
    if isinstance(evaluation, dict):
        evaluation["score"] = score
        evaluation["grade"] = grade
    if "status" in updated:
        updated["status"] = status
    return updated


def _payload_direction(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for value in payload.get("kpi_values") or []:
        if isinstance(value, dict) and value.get("kpi_key") == KPI_KEY:
            return value.get("direction")
    return None


def run(db: Session, *, apply: bool = False) -> dict[str, Any]:
    """Plan (and with ``apply`` write) the correction. Returns a report dict."""
    thresholds = load_team_config(TEAM_NAME).get("grade_thresholds")
    team_ids = [team.id for team in db.query(Team).filter(Team.name == TEAM_NAME).all()]
    report: dict[str, Any] = {
        "apply": apply,
        "records_checked": 0,
        "records_to_fix": 0,
        "already_correct": 0,
        "payload_direction_only": 0,
        "unexpected": 0,
        "team_kpi_config_to_fix": 0,
        "changes": [],
        "unexpected_rows": [],
    }
    if not team_ids:
        return report

    rows = (
        db.query(PerformanceRecord, KPIValue)
        .join(
            KPIValue,
            (KPIValue.record_id == PerformanceRecord.id) & (KPIValue.record_year == PerformanceRecord.year),
        )
        .filter(PerformanceRecord.team_id.in_(team_ids), KPIValue.kpi_key == KPI_KEY)
        .all()
    )
    for record, value in rows:
        report["records_checked"] += 1
        actual = _decimal(value.actual_value)
        target = _decimal(value.target_value)
        weight = _decimal(value.weight_applied)
        stored = _decimal(value.contribution)
        old_effective = _effective(actual, target, OLD_DIRECTION)
        new_effective = _effective(actual, target, NEW_DIRECTION)
        old_contribution = old_effective * weight
        new_contribution = new_effective * weight
        payload_direction = _payload_direction(record.record_payload)

        if abs(stored - new_contribution) <= TOLERANCE and (
            abs(old_contribution - new_contribution) > TOLERANCE or payload_direction != OLD_DIRECTION
        ):
            report["already_correct"] += 1
            continue
        if abs(stored - old_contribution) > TOLERANCE:
            report["unexpected"] += 1
            report["unexpected_rows"].append(
                {"record_id": str(record.id), "year": record.year, "month": record.month,
                 "stored_contribution": float(stored), "old_rule": float(_q4(old_contribution)),
                 "new_rule": float(_q4(new_contribution))}
            )
            continue

        old_score = _decimal(record.score)
        delta_points = (new_contribution - old_contribution) * Decimal("100")
        new_score = (old_score + delta_points).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        new_score = max(Decimal("0"), min(new_score, Decimal("100")))
        new_grade = calculate_grade(float(new_score), thresholds)
        new_status = _status(new_grade)
        score_changes = abs(delta_points) > Decimal("0.005")
        if score_changes:
            report["records_to_fix"] += 1
        else:
            report["payload_direction_only"] += 1
        report["changes"].append(
            {
                "record_id": str(record.id), "year": record.year, "month": record.month,
                "actual": float(actual), "target": float(target), "weight": float(weight),
                "contribution": [float(stored), float(_q4(new_contribution))],
                "achievement_ratio": [float(value.achievement_ratio), float(_q4(new_effective))],
                "score": [float(old_score), float(new_score)],
                "grade": [record.grade, new_grade],
                "status": [record.status, new_status],
            }
        )
        if apply:
            value.achievement_ratio = _q4(new_effective)
            value.contribution = _q4(new_contribution)
            record.score = new_score
            record.grade = new_grade
            record.status = new_status
            record.record_payload = _patched_payload(
                record.record_payload,
                ratio=float(_q4(new_effective)),
                contribution=float(_q4(new_contribution)),
                score=float(new_score),
                grade=new_grade,
                status=new_status,
            )

    configs = (
        db.query(TeamKPIConfig)
        .filter(TeamKPIConfig.team_id.in_(team_ids), TeamKPIConfig.kpi_key == KPI_KEY)
        .all()
    )
    for config_row in configs:
        if config_row.direction != NEW_DIRECTION:
            report["team_kpi_config_to_fix"] += 1
            if apply:
                config_row.direction = NEW_DIRECTION

    if apply:
        db.flush()
    return report


def _print_report(report: dict[str, Any]) -> None:
    mode = "APPLY" if report["apply"] else "DRY RUN (nothing written)"
    print(f"cw_error_free direction fix - {mode}")
    for key in ("records_checked", "records_to_fix", "payload_direction_only", "already_correct", "unexpected", "team_kpi_config_to_fix"):
        print(f"  {key}: {report[key]}")
    for change in report["changes"]:
        print(
            f"  record {change['record_id']} {change['month']} {change['year']}: "
            f"score {change['score'][0]} -> {change['score'][1]}, grade {change['grade'][0]} -> {change['grade'][1]}, "
            f"contribution {change['contribution'][0]} -> {change['contribution'][1]}"
        )
    for row in report["unexpected_rows"]:
        print(f"  UNEXPECTED (left unchanged, review manually): {row}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = parser.parse_args(argv)

    from config.database import SessionLocal

    with SessionLocal() as db:
        try:
            report = run(db, apply=args.apply)
            if args.apply:
                db.commit()
            else:
                db.rollback()
        except Exception:
            db.rollback()
            raise
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
