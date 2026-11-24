"""Prepare a dated CSR upload from the four UAE monthly report tabs.

Run from Backend with: python -m scripts.prepare_csr_source_upload
    --report <monthly report.xlsx> --period YYYY-MM --output <new upload.xlsx>
"""

import argparse
import re
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.utils import column_index_from_string


COMMON_BRANCH_COLUMNS = {
    "HR ID": ("B", "EID"),
    "Agent Name": ("C", "Employee Name"),
    "Status": ("D", "Staff Status"),
    "No of Billing": ("H", "No of Billing"),
    "A.CSR Queries": ("M", "CSR Queries"),
    "A.CSR Rejection %": ("S", "CSR Rejection %"),
    "A.CPT Conversion %": ("P", "CPT Conversion %"),
    "T.CSR Rejection %": ("T", "CSR Rejection target %"),
    "T.Queries Target": ("U", "Queries Target"),
    "T.Attended C.R": ("V", "Attended C.R"),
    "Serving Time (min)": ("R", "Serving Time (Target 5M)"),
    "No of Complaints": ("Z", "No of Complains"),
    "Performance Score": ("AC", "Performance Score"),
    "Performance Grade": ("AD", "Performance Grade"),
}

SOURCE_TABS = {
    "CSR - Dubai": ("Dubai", {
        "HR ID": ("B", "Employee ID"),
        "Agent Name": ("D", "Employee Name"),
        "Status": ("G", "Employee Status"),
        "No of Billing": ("H", "No of Billing"),
        "A.CSR Queries": ("R", "CSR Queries"),
        "A.CSR Rejection %": ("S", "CSR Rejection %"),
        "A.CPT Conversion %": ("T", "CPT Conversion %"),
        "T.CSR Rejection %": ("U", "CSR Rejection %"),
        "T.Queries Target": ("V", "Queries Target"),
        "T.Attended C.R": ("W", "Attended C.R"),
        "Serving Time (min)": ("Q", "Serving Time"),
        "No of Complaints": ("X", "Complain"),
        "Performance Score": ("AC", "Performance Score"),
        "Performance Grade": ("AD", "Performance Grade"),
    }),
    "CSR - ER - Dubai": ("Dubai", {
        "HR ID": ("B", "EID"),
        "Agent Name": ("C", "Employee Name"),
        "Status": ("D", "Staff Status"),
        "No of Billing": ("G", "No of Billing"),
        "A.CSR Queries": ("L", "CSR Queries"),
        "A.CSR Rejection %": ("O", "CSR Rejection %"),
        "T.CSR Rejection %": ("P", "CSR Rejection target %"),
        "T.Queries Target": ("Q", "Queries Target"),
        "T.Attended C.R": ("R", "Attended C.R"),
        "No of Complaints": ("U", "No of Complains"),
        "Performance Score": ("W", "Performance Score"),
        "Performance Grade": ("X", "Performance Grade"),
    }),
    "CSR AJM": ("AJM", COMMON_BRANCH_COLUMNS),
    "CSR SHJ": ("SHJ", COMMON_BRANCH_COLUMNS),
}
OUTPUT_COLUMNS = ("Date", "Region", "Role", "Team", "CSR Source Sheet", *COMMON_BRANCH_COLUMNS)
UNSCORED_LABELS = {"-", "inactive", "inactive staff", "leave", "new staff", "active - new"}


def _label(value) -> str:
    return " ".join(str(value or "").casefold().split())


def prepare_upload(report_path: Path, period: date, output_path: Path) -> int:
    source = load_workbook(report_path, read_only=True, data_only=True)
    upload = Workbook()
    sheet = upload.active
    sheet.title = "CSR"
    sheet.append(OUTPUT_COLUMNS)
    seen: set[str] = set()
    try:
        for title, (branch, columns) in SOURCE_TABS.items():
            if title not in source:
                raise ValueError(f"Monthly report is missing {title}")
            worksheet = source[title]
            for column, expected in columns.values():
                if _label(worksheet[f"{column}2"].value) != _label(expected):
                    raise ValueError(f"{title}!{column}2 must contain {expected!r}")
            indices = {
                target: column_index_from_string(column) - 1
                for target, (column, _) in columns.items()
            }
            for row_number, row in enumerate(worksheet.iter_rows(min_row=3, values_only=True), 3):
                data = {target: row[index] for target, index in indices.items()}
                employee = str(data["HR ID"] or "").strip().upper()
                if not re.fullmatch(r"SG[A-Z]+[0-9]+", employee):
                    continue
                if {_label(data["Status"]), _label(data["Performance Grade"])} & UNSCORED_LABELS:
                    continue
                score = data["Performance Score"]
                if score is None or (isinstance(score, str) and _label(score) in {"", "-", "na", "n/a"}):
                    continue
                if type(score) not in (int, float):
                    raise ValueError(f"{title} row {row_number} has an invalid cached Performance Score")
                if employee in seen:
                    raise ValueError(f"{title} row {row_number} repeats an already scored employee")
                seen.add(employee)
                data["HR ID"] = employee
                data.update({"Date": period, "Region": "UAE", "Role": "Employee", "Team": branch, "CSR Source Sheet": title})
                sheet.append([data.get(column) for column in OUTPUT_COLUMNS])
    finally:
        source.close()
    if not seen:
        raise ValueError("Monthly report contains no scored CSR employee rows")
    with output_path.open("xb") as destination:
        upload.save(destination)
    return len(seen)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--period", required=True, help="The source report month in YYYY-MM format")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", args.period):
            raise ValueError("period must be YYYY-MM")
        period = date.fromisoformat(f"{args.period}-01")
        if (period.year, period.month) < (2026, 10):
            raise ValueError("the monthly CSR scorecard import starts in October 2026")
        count = prepare_upload(args.report, period, args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Prepared {count} CSR employee scores for {args.period}.")


if __name__ == "__main__":
    main()
