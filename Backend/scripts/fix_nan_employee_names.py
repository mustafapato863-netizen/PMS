"""Repair employee records and performance payloads where employee name was saved as 'nan'.

When older sheets (e.g. Coding) had missing AgentName cells in Excel, they were
read as NaN by pandas and string-cast to 'nan'. This script:
1. Recovers real employee names from record_payload where available.
2. Falls back to employee_id for records with no name in the source data.
3. Cleans up performance_record payloads to remove literal 'nan' names.

Usage (from Backend/):
    python -m scripts.fix_nan_employee_names          # dry run
    python -m scripts.fix_nan_employee_names --apply  # write changes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.database import SessionLocal  # noqa: E402
from models.models import Employee, PerformanceRecord  # noqa: E402


def is_nan_like(value: str | None) -> bool:
    if not value:
        return True
    return str(value).strip().lower() in {"", "nan", "none", "null"}


def run_repair(apply_changes: bool = False) -> None:
    session = SessionLocal()
    try:
        employees = session.query(Employee).all()
        nan_employees = [e for e in employees if is_nan_like(e.name)]
        print(f"Found {len(nan_employees)} employees with 'nan' or empty names out of {len(employees)} total.")

        recovered_count = 0
        fallback_count = 0
        records_updated = 0

        for emp in nan_employees:
            records = session.query(PerformanceRecord).filter(PerformanceRecord.employee_id == emp.id).all()
            real_name = None
            for rec in records:
                if rec.record_payload and isinstance(rec.record_payload, dict):
                    cand = str(rec.record_payload.get("employee_name") or "").strip()
                    if not is_nan_like(cand):
                        real_name = cand
                        break

            new_name = real_name if real_name else str(emp.employee_id)
            if real_name:
                recovered_count += 1
            else:
                fallback_count += 1

            if apply_changes:
                emp.name = new_name
                # Also synchronize record_payload for all records belonging to this employee
                for rec in records:
                    if rec.record_payload and isinstance(rec.record_payload, dict):
                        payload_name = str(rec.record_payload.get("employee_name") or "").strip()
                        if is_nan_like(payload_name):
                            updated_payload = dict(rec.record_payload)
                            updated_payload["employee_name"] = new_name
                            rec.record_payload = updated_payload
                            records_updated += 1

        if apply_changes:
            session.commit()
            print(f"Successfully applied changes! Updated {len(nan_employees)} employees ({recovered_count} recovered real names, {fallback_count} assigned employee_id), and updated {records_updated} record payloads.")
        else:
            print(f"Dry run complete. Would update {len(nan_employees)} employees ({recovered_count} recovered real names, {fallback_count} assigned employee_id). Run with --apply to commit.")

    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair 'nan' employee names.")
    parser.add_argument("--apply", action="store_true", help="Apply updates to database.")
    args = parser.parse_args()
    run_repair(apply_changes=args.apply)


if __name__ == "__main__":
    main()
