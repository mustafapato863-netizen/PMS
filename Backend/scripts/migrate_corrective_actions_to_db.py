"""Import legacy corrective-action JSON files into the canonical actions table.

The command is a dry-run unless --apply is provided. Re-running it is safe:
records are deduplicated by employee, period, type, text, note, and timestamp.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy import and_


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.database import SessionLocal  # noqa: E402
from models.models import Action, Employee, User  # noqa: E402
from services.corrective_action_service import CorrectiveActionService  # noqa: E402


def _timestamp(value: object) -> dt.datetime:
    if isinstance(value, str) and value.strip():
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc)


def _employee(db, identifier: str) -> Employee | None:
    employee = db.query(Employee).filter(Employee.employee_id == identifier).first()
    if employee or not identifier.upper().startswith(("SGHD", "SGHA")):
        return employee
    return db.query(Employee).filter(Employee.employee_id == identifier[4:]).first()


def _load_sources(paths: list[Path]) -> list[dict]:
    records: list[dict] = []
    for path in paths:
        with path.open("r", encoding="utf-8-sig") as source:
            payload = json.load(source)
        if not isinstance(payload, list):
            raise ValueError(f"{path} must contain a JSON array")
        records.extend(item for item in payload if isinstance(item, dict))
    return records


def migrate(paths: list[Path], *, apply: bool, deactivate_empty_legacy: bool) -> dict[str, int]:
    source_records = _load_sources(paths)
    counters = {"source": len(source_records), "inserted": 0, "skipped": 0, "missing_employee": 0, "deactivated_empty": 0}
    seen: set[tuple] = set()

    with SessionLocal() as db:
        try:
            if deactivate_empty_legacy:
                empty_actions = db.query(Action).filter(
                    Action.is_active.is_(True),
                    Action.action_text == "",
                ).all()
                for action in empty_actions:
                    action.is_active = False
                counters["deactivated_empty"] = len(empty_actions)

            for item in source_records:
                identifier = str(item.get("employee_id") or "").strip()
                employee = _employee(db, identifier)
                if not employee:
                    counters["missing_employee"] += 1
                    continue

                manager_action = str(item.get("manager_action") or "").strip()
                if not manager_action:
                    counters["skipped"] += 1
                    continue
                action_type, action_text = CorrectiveActionService.split_manager_action(manager_action)
                note = str(item.get("manager_notes") or "").strip() or None
                created_at = _timestamp(item.get("timestamp"))
                month = str(item.get("month") or "").strip()
                year = int(item.get("year") or created_at.year)
                fingerprint = (employee.id, month, year, action_type, action_text, note, created_at.isoformat())
                if fingerprint in seen:
                    counters["skipped"] += 1
                    continue
                seen.add(fingerprint)

                existing = db.query(Action.id).filter(and_(
                    Action.employee_id == employee.id,
                    Action.month == month,
                    Action.year == year,
                    Action.action_type == action_type,
                    Action.action_text == action_text,
                    Action.root_cause_note == note,
                    Action.created_at == created_at,
                )).first()
                if existing:
                    counters["skipped"] += 1
                    continue

                creator = None
                creator_name = str(item.get("created_by_name") or "").strip()
                if creator_name:
                    creator = db.query(User).filter(User.username == creator_name).first()
                db.add(Action(
                    employee_id=employee.id,
                    team_id=employee.team_id,
                    month=month,
                    year=year,
                    action_type=action_type,
                    action_text=action_text,
                    root_cause_note=note,
                    status="Open",
                    is_active=True,
                    created_by_user_id=creator.id if creator else None,
                    created_at=created_at,
                ))
                counters["inserted"] += 1

            db.flush()
            counters["active_after"] = db.query(Action).filter(Action.is_active.is_(True)).count()
            if apply:
                db.commit()
            else:
                db.rollback()
            return counters
        except Exception:
            db.rollback()
            raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--deactivate-empty-legacy", action="store_true")
    args = parser.parse_args()

    result = migrate(
        [path.resolve() for path in args.source],
        apply=args.apply,
        deactivate_empty_legacy=args.deactivate_empty_legacy,
    )
    mode = "APPLIED" if args.apply else "DRY RUN (ROLLED BACK)"
    print(mode)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
