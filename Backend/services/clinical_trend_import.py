"""Import report-calculated employee scores for the new clinical trend sheets."""
import math
import re

import pandas as pd

from models.schemas import Employee, EvaluationData, PerformanceRecord
from services.clinical_scorecards import can_recompute, compute_clinical_score
from utils.helpers import safe_value


TEAMS = ("ER Dr", "Radiologist", "Qlty&Case-Mngt")
FIRST_PERIOD = pd.Timestamp("2026-10-01")
GRADE_LABELS = {
    "excellent": "A", "meet expectations": "B", "average": "C",
    "below average": "D", "unsatisfactory": "E",
    "a": "A", "b": "B", "c": "C", "d": "D", "e": "E",
}


def _clinical_frame(excel_file, team):
    if team != "ER Dr":
        return pd.read_excel(excel_file, sheet_name=team)

    # The right-hand block has the current 24-hour revisit measure. Older
    # 72-hour columns stay in the historical table in the workbook.
    source = pd.read_excel(excel_file, sheet_name=team, header=None)
    header = source.iloc[1].tolist() if len(source) > 1 else []
    start = next((index for index, value in enumerate(header) if value == "Report Month"), None)
    if start is None:
        return pd.read_excel(excel_file, sheet_name=team)
    end = next((index for index, value in enumerate(header[start:], start)
                if value == "Performance Grade"), None)
    required = {"EmpID", "Emp Name", "Performance Score", "Location"}
    if end is None or not required.issubset(header[start:end + 1]):
        raise ValueError("ER Dr trend block is missing one or more required headers")
    frame = source.iloc[2:, start:end + 1].copy()
    repeated = {}
    names = []
    for label in header[start:end + 1]:
        repeated[label] = repeated.get(label, 0) + 1
        occurrence = repeated[label]
        names.append(f"{label}.{occurrence}" if occurrence > 1 else label)
    frame.columns = names
    return frame.rename(columns={"Report Month": "Date", "EmpID": "HR ID", "Emp Name": "Agent Name"})


# These columns are the workbook's achieved KPI scores. The ER block
# repeats labels for actual, target and achievement in that order.
_ER_ACHIEVEMENTS = {
    "Valid Complains": "Valid complaints",
    "Satisfaction Score.3": "Satisfaction",
    "LAMA Retention %.2": "LAMA retention",
    "Admission Rate %.2": "Admission rate",
    "Re-visit Rate  %.2": "24-hour revisit rate",
    "Avg Time to Initial Patient Assessment 10%": "Time to initial patient assessment",
    "Medical Error Rate ": "Medical error rate",
    "Documentation%.3": "Documentation",
}
_QUALITY_ACHIEVEMENTS = {
    "Audit Compliance Rate % (IP, OP, Re-Submission)": "Audit compliance",
    "Rejection Rate": "Rejection rate",
    "Case Management Rate": "Case management",
    "Revenue Impact": "Revenue impact",
}


def clinical_measurements(team, raw):
    """Expose source achievement separately from the published employee score."""
    if not isinstance(raw, dict):
        return []
    if team == "ER Dr":
        columns = _ER_ACHIEVEMENTS
    elif team == "Qlty&Case-Mngt":
        columns = _QUALITY_ACHIEVEMENTS
    elif team == "Radiologist":
        columns = {key: key[4:].strip().rstrip("%").strip() for key in raw if key.startswith("Ach.")}
    else:
        return []
    measurements = []
    for column, label in columns.items():
        try:
            value = float(raw.get(column))
        except (ValueError, TypeError):
            continue
        if not math.isfinite(value) or value < 0:
            continue
        key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        measurements.append({
            "kpi_key": f"achievement_{key}", "label": f"{label} achievement",
            "direction": "higher_better", "unit": "%", "actual_value": value,
            "target_value": 1.0, "achievement_ratio": min(value, 1),
            "weight_applied": 0, "contribution": 0, "view_only": True,
        })
    return measurements


def import_clinical_trend(excel_file):
    records, employees = [], []
    for team in TEAMS:
        if team not in excel_file.sheet_names:
            continue
        frame = _clinical_frame(excel_file, team)
        if not {"Date", "HR ID", "Performance Score"}.issubset(frame.columns):
            raise ValueError(f"{team} trend sheet is missing Date, HR ID or Performance Score")
        for row in frame.to_dict("records"):
            date = pd.to_datetime(row["Date"], errors="coerce")
            eid = str(row["HR ID"]).strip()
            if pd.isna(date) or date < FIRST_PERIOD or not re.fullmatch(r"SG[A-Z]+[0-9]+", eid, re.I):
                continue
            if pd.isna(row["Performance Score"]) or str(row["Performance Score"]).strip() in {"", "-", "NA", "N/A"}:
                continue
            try:
                score = float(row["Performance Score"])
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{team} has a nonnumeric performance score for {eid}") from exc
            if not math.isfinite(score):
                raise ValueError(f"{team} has a nonfinite performance score for {eid}")
            # The trend columns store Excel percentage fractions, including 0.
            score = min(100.0, max(0.0, round(score * 100, 2)))
            grade = GRADE_LABELS.get(str(row.get("Performance Grade")).strip().casefold())
            if not grade:
                raise ValueError(f"{team} has a valid score but no recognized performance grade for {eid}")
            name = next((str(row[col]).strip() for col in ("Employee Name", "Agent Name")
                         if col in row and pd.notna(row[col]) and str(row[col]).strip()), eid)
            position = str(row["Position"]).strip() if pd.notna(row.get("Position")) else None
            status = next((str(row[col]).strip() for col in ("Status", "Staff Status")
                           if col in row and pd.notna(row[col]) and str(row[col]).strip()), "Active")
            raw = {str(key): safe_value(value) for key, value in row.items()}
            if pd.notna(row.get("Location")):
                raw["Branch"] = raw["Location"]
            month = date.strftime("%B")

            # Attempt to recompute score from source KPIs
            recomputed = compute_clinical_score(team, raw) if can_recompute(team, raw) else None
            if recomputed is not None:
                recomputed_score, recomputed_grade, recomputed_kpis = recomputed
                use_score = recomputed_score
                use_grade = recomputed_grade
                kpi_list = recomputed_kpis
            else:
                use_score = score
                use_grade = grade
                kpi_list = [{
                    "kpi_key": "PerformanceScore", "label": "Performance Score",
                    "direction": "higher_better",
                    "actual_value": score / 100, "target_value": 1,
                    "achievement_ratio": score / 100,
                    "weight_applied": 1, "contribution": score / 100,
                }, *clinical_measurements(team, raw)]

            employees.append(Employee(id=eid, name=name, team=team, status=status,
                                      region="UAE", performance_level="Employee", position=position))
            records.append(PerformanceRecord(
                id=f"{eid}_{date.year}_{month}", employee_id=eid, employee_name=name, team=team,
                month=month, year=date.year, region="UAE", position=position,
                evaluation=EvaluationData(score=use_score, grade=use_grade), raw_data=raw,
                kpi_values=kpi_list,
            ))
    return records, employees
