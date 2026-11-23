"""Sharjah CSR employee scorebook effective October 2026."""
import math

from data_cleaning.standard_mappings import calculate_grade
from services.preapprovals_offshore_scoring import reporting_period_from_row
from utils.branch_scope import explicit_branch_key


METHOD_ID = "csr_sharjah_october_2026"
SERVING_TIME_COLUMN = "ServingTime(min)"
COMPLAINT_COUNT_COLUMN = "NoofComplaints"
SOURCE_COLUMNS = ("Serving Time (min)", "No of Complaints")
GRADE_THRESHOLDS = {"A": 100, "B": 89, "C": 79, "D": 69}
SERVING_TIME_TARGET = 5.0
COMPLAINT_PENALTY = 0.20


def uses_sharjah_csr_score(row, performance_level):
    if performance_level != "Employee" or explicit_branch_key({"raw_data": row}) != "sharjah":
        return False
    period = reporting_period_from_row(row)
    return period is not None and period >= (2026, 10)


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _required(row, column):
    value = _number(row.get(column))
    if value is None:
        raise ValueError(f"Sharjah CSR requires a non-negative value in {column} from October 2026")
    return value


def _lower_better(actual, target):
    return 1.0 if actual == 0 else min(target / actual, 1.0)


def score_sharjah_csr(row):
    rejection = _required(row, "A.CSRRejection%")
    rejection_target = _required(row, "T.CSRRejection%")
    queries = _required(row, "A.CSRQueries")
    queries_target = _required(row, "T.QueriesTarget")
    complaints = _required(row, COMPLAINT_COUNT_COLUMN)
    if not complaints.is_integer():
        raise ValueError("Sharjah CSR No of Complaints must be a whole number")

    serving = _number(row.get(SERVING_TIME_COLUMN))
    attended = _number(row.get("A.CPTConversion%"))
    attended_target = _number(row.get("T.AttendedC.R"))
    has_attended = attended is not None and attended_target is not None and attended_target > 0
    has_serving = serving is not None
    # Source scorebook reweights the present measures for each availability case.
    rejection_weight, queries_weight, attended_weight, serving_weight = {
        (False, False): (0.60, 0.40, 0.0, 0.0),
        (False, True): (0.40, 0.25, 0.0, 0.35),
        (True, False): (0.40, 0.30, 0.30, 0.0),
        (True, True): (0.30, 0.20, 0.20, 0.30),
    }[has_attended, has_serving]

    def evidence(key, label, actual, target, ratio, weight, direction, unit):
        return {
            "kpi_key": key, "label": label, "unit": unit, "direction": direction,
            "actual_value": actual, "target_value": target, "achievement_ratio": ratio,
            "weight_applied": weight, "contribution": ratio * weight,
        }

    rows = [
        evidence("Rejection", "Rejection", rejection, rejection_target,
                 _lower_better(rejection, rejection_target), rejection_weight, "lower_better", "%"),
        evidence("Queries", "Queries Handled", queries, queries_target,
                 _lower_better(queries, queries_target), queries_weight, "lower_better", "%"),
    ]
    if has_attended:
        rows.append(evidence("AttendedCR", "Attended CR", attended, attended_target,
                             min(attended / attended_target, 1.0), attended_weight, "higher_better", "%"))
    if has_serving:
        rows.append(evidence("ServingTime", "Serving Time", serving, SERVING_TIME_TARGET,
                             _lower_better(serving, SERVING_TIME_TARGET), serving_weight, "lower_better", "min"))
    penalty = evidence("Complaints", "Complaints", complaints, 0, float(complaints == 0),
                       0, "lower_better", "count")
    penalty["contribution"] = -complaints * COMPLAINT_PENALTY
    rows.append(penalty)
    score = round(max(sum(item["contribution"] for item in rows), 0.0) * 100, 2)
    return score, calculate_grade(score, GRADE_THRESHOLDS), rows
