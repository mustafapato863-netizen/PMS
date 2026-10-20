"""One upload of the management template feeds two stores.

Corporate rows update the balanced scorecard and clear older non-Corporate
rows from it. Employee and Managerial rows become position-based department
records. The workbook is repaired before either store is written.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from services.bsc_template_service import bsc_template_service
from services.management_bsc_service import ManagementBSCService
from services.management_template_repair import repair_workbook_bytes
from services.position_department_import_service import PositionDepartmentImportService

DEPARTMENT_LEVELS = frozenset({"Employee", "Managerial"})


def import_uploaded_management_template(
    db: Session,
    contents: bytes,
    *,
    updated_by: str | None = None,
    source_filename: str | None = None,
) -> dict:
    repaired = repair_workbook_bytes(contents)
    rows, warnings = bsc_template_service.parse_upload_with_warnings(repaired)
    corporate = [row for row in rows if row.get("performance_level") == "Corporate"]
    departmental = [row for row in rows if row.get("performance_level") in DEPARTMENT_LEVELS]
    try:
        management = ManagementBSCService(db).import_template_rows(
            rows=corporate,
            updated_by=updated_by,
            source_filename=source_filename,
            purge_non_corporate=True,
            commit=False,
        )
        position = PositionDepartmentImportService(db).import_parsed_rows(departmental, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        **management,
        "rows": rows,
        "warnings": warnings,
        "position_records": position["records"],
        "position_teams": position["teams"],
    }
