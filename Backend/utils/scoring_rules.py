"""Shared score rules: scale and grade cut-offs.

Stored evaluation scores are percentages. One rule for every team: a value in
(0, 1] is a ratio and is multiplied by 100 (0.85 -> 85). A value above 1 is already
a percentage and is used as it is, so a low real score such as 5.48 stays 5.48 and
a percentage such as 51.28 is returned unchanged.

The grade cut-offs are the shared thresholds (frontend `constants/grades.ts`):
A >= 95, B >= 90, C >= 80, D >= 70, E below 70.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, case

# One matrix for every team and every performance level:
# A Excellent >= 95, B Meet Expectations >= 90, C Average >= 80,
# D Below Average >= 70, E Unsatisfactory below 70.
GRADE_THRESHOLD_MAP: dict[str, float] = {"A": 95.0, "B": 90.0, "C": 80.0, "D": 70.0}
GRADE_THRESHOLDS: tuple[tuple[str, float], ...] = tuple(GRADE_THRESHOLD_MAP.items())


def score_percent(score: float) -> float:
    """Return the percentage form of a stored score (the only score-scale rule on the server)."""
    return score * 100 if 0 < score <= 1 else score


def score_percent_sql(column: Any) -> Any:
    """SQL form of :func:`score_percent` for ordering and filtering in the database."""
    return case((and_(column > 0, column <= 1), column * 100), else_=column)


def letter_grade(score: float) -> str:
    """Grade letter for a percentage score, using :data:`GRADE_THRESHOLDS`."""
    for letter, threshold in GRADE_THRESHOLDS:
        if score >= threshold:
            return letter
    return "E"
