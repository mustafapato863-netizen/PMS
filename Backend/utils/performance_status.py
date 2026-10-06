"""Record status derived from grade (the rule every import path uses).

``A`` -> ``Exceeds``, ``B``/``C`` -> ``Meets``, anything else -> ``Below``.
Shared by uploads, the Marketing import, read-time score reconciliation and
the data-fix scripts so a corrected grade always maps to the same status.
"""

from __future__ import annotations

GRADE_STATUSES = frozenset({"Exceeds", "Meets", "Below"})


def status_for_grade(grade: str | None) -> str:
    if grade == "A":
        return "Exceeds"
    if grade in {"B", "C"}:
        return "Meets"
    return "Below"


def reconciled_status(stored_status: str | None, stored_grade: str | None, grade: str | None) -> str | None:
    """Status to show after a read-time grade correction.

    The status is recomputed only when the grade changed and the stored status
    was the grade-derived one (or blank); a custom stored status is kept.
    """
    if grade == stored_grade:
        return stored_status
    if not stored_status or (stored_status in GRADE_STATUSES and stored_status == status_for_grade(stored_grade)):
        return status_for_grade(grade)
    return stored_status
