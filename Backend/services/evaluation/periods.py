"""Exact reporting-month helpers. There is no latest-month or future-month fallback."""

from __future__ import annotations

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


class PeriodError(ValueError):
    pass


def month_number(value) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        number = value
    else:
        text = str(value or "").strip()
        if not text:
            raise PeriodError("Reporting month is required.")
        if text.isdigit():
            number = int(text)
        else:
            lowered = text.casefold()
            number = next((index for index, name in enumerate(MONTHS, start=1) if name.casefold() == lowered or name.casefold()[:3] == lowered), 0)
    if number < 1 or number > 12:
        raise PeriodError("Reporting month must be an exact calendar month.")
    return number


def month_name(value) -> str:
    return MONTHS[month_number(value) - 1]


def previous_period(year: int, month: int) -> tuple[int, int]:
    number = month_number(month)
    if number == 1:
        return int(year) - 1, 12
    return int(year), number - 1


def month_aliases(value) -> set[str]:
    number = month_number(value)
    name = MONTHS[number - 1]
    return {name, name.casefold(), str(number), f"{number:02d}"}
