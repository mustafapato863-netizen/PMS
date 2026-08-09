from enum import Enum

class PerformanceLevel(str, Enum):
    EMPLOYEE = "Employee"
    MANAGERIAL = "Managerial"
    CORPORATE = "Corporate"

PERFORMANCE_LEVELS = (PerformanceLevel.EMPLOYEE.value, PerformanceLevel.MANAGERIAL.value, PerformanceLevel.CORPORATE.value)

PERFORMANCE_LEVEL_ALIASES = {
    "emp": PerformanceLevel.EMPLOYEE.value,
    "employee": PerformanceLevel.EMPLOYEE.value,
    "manager": PerformanceLevel.MANAGERIAL.value,
    "managerial": PerformanceLevel.MANAGERIAL.value,
    "corp": PerformanceLevel.CORPORATE.value,
    "corporate": PerformanceLevel.CORPORATE.value,
}


def normalize_performance_level(value, *, allow_all: bool = False) -> str:
    normalized = "" if value is None else str(value).strip().lower()
    if allow_all and (not normalized or normalized == "all"):
        return "All"
    try:
        return PERFORMANCE_LEVEL_ALIASES[normalized]
    except KeyError as exc:
        accepted = ", ".join(PERFORMANCE_LEVEL_ALIASES)
        raise ValueError(f"Invalid performance level {value!r}. Accepted values: {accepted}") from exc
