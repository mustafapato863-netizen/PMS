"""Repair employee records and performance payloads where employee name was saved as 'nan' or employee_id.

When older sheets (e.g. Inbound, Outbound, CSR, Coding) lacked an AgentName column
or had NaN values in Excel, employees were initialized with their employee_id or 'nan'.
This script:
1. Loads real English names from the Manpower sheet in the trend workbook.
2. Recovers employee names from record_payload where available.
3. Updates Employee.name in the database.
4. Updates record_payload["employee_name"] on all corresponding PerformanceRecords.
5. Bumps CacheInvalidationService data version so the UI immediately reflects real names.

Usage (from Backend/):
    python -m scripts.fix_nan_employee_names          # dry run
    python -m scripts.fix_nan_employee_names --apply  # write changes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.database import SessionLocal  # noqa: E402
from models.models import Employee, PerformanceRecord  # noqa: E402
from services.cache_invalidation_service import CacheInvalidationService  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402


def is_nan_like(value: str | None) -> bool:
    if not value:
        return True
    return str(value).strip().lower() in {"", "nan", "none", "null"}


def load_manpower_directory(workbook_path: Path) -> Dict[str, str]:
    if not workbook_path.is_file():
        return {}
    import openpyxl

    wb = openpyxl.load_workbook(str(workbook_path), read_only=True, data_only=True)
    if "Manpower" not in wb.sheetnames:
        return {}
    ws = wb["Manpower"]
    directory: Dict[str, str] = {}
    for row in ws.iter_rows(values_only=True):
        if len(row) > 13 and row[12] and row[13]:
            code = str(row[12]).strip().upper()
            name = str(row[13]).strip()
            if code and name and code != "CODE" and not is_nan_like(name):
                directory[code] = name
    return directory


def run_repair(workbook_path: Path | None = None, apply_changes: bool = False) -> None:
    target_path = workbook_path or Path(r"D:\Trend\PMS_Trend_All.xlsx")
    manpower_map = load_manpower_directory(target_path)
    print(f"Loaded {len(manpower_map)} employee names from Manpower sheet at {target_path}")

    session = SessionLocal()
    try:
        employees = session.query(Employee).all()
        recovered_manpower = 0
        recovered_payload = 0
        fallback_count = 0
        records_updated = 0
        employees_to_update = []

        for emp in employees:
            curr_name = str(emp.name or "").strip()
            is_unresolved = is_nan_like(curr_name) or curr_name.upper() == str(emp.employee_id).strip().upper()

            # 1. First priority: Manpower sheet
            manpower_name = manpower_map.get(str(emp.employee_id).strip().upper())

            # 2. Second priority: Existing non-nan record payload
            payload_name = None
            records = session.query(PerformanceRecord).filter(PerformanceRecord.employee_id == emp.id).all()
            for rec in records:
                if rec.record_payload and isinstance(rec.record_payload, dict):
                    cand = str(rec.record_payload.get("employee_name") or "").strip()
                    if not is_nan_like(cand) and cand.upper() != str(emp.employee_id).strip().upper():
                        payload_name = cand
                        break

            chosen_name = None
            if manpower_name:
                chosen_name = manpower_name
                if is_unresolved:
                    recovered_manpower += 1
            elif payload_name:
                chosen_name = payload_name
                if is_unresolved:
                    recovered_payload += 1
            elif is_unresolved:
                chosen_name = str(emp.employee_id)
                fallback_count += 1

            if chosen_name and (is_unresolved or (manpower_name and curr_name != manpower_name)):
                employees_to_update.append((emp, chosen_name, records))

        print(
            f"Found {len(employees_to_update)} employees to update:\n"
            f"  - {recovered_manpower} from Manpower directory\n"
            f"  - {recovered_payload} from record payloads\n"
            f"  - {fallback_count} fell back to employee code"
        )

        for emp, new_name, records in employees_to_update:
            if apply_changes:
                emp.name = new_name
            for rec in records:
                payload = dict(rec.record_payload) if isinstance(rec.record_payload, dict) else {}
                old_pname = str(payload.get("employee_name") or "").strip()
                if old_pname != new_name:
                    if apply_changes:
                        payload["employee_name"] = new_name
                        if "raw_data" in payload and isinstance(payload["raw_data"], dict):
                            payload["raw_data"]["employee_name"] = new_name
                        rec.record_payload = payload
                        flag_modified(rec, "record_payload")
                    records_updated += 1

        if apply_changes:
            session.commit()
            CacheInvalidationService.bump_data_version()
            print(
                f"Successfully applied changes!\n"
                f"Updated {len(employees_to_update)} employees and {records_updated} performance record payloads.\n"
                f"Bumped cache data version."
            )
        else:
            print(
                f"Dry run complete. Would update {len(employees_to_update)} employees and {records_updated} record payloads.\n"
                f"Run with --apply to commit."
            )

    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair 'nan' and code-only employee names.")
    parser.add_argument("--workbook", type=Path, default=Path(r"D:\Trend\PMS_Trend_All.xlsx"), help="Path to workbook.")
    parser.add_argument("--apply", action="store_true", help="Apply updates to database.")
    args = parser.parse_args()
    run_repair(workbook_path=args.workbook, apply_changes=args.apply)


if __name__ == "__main__":
    main()
