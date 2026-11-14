"""Calendar cohort handling for explicitly named months."""

import calendar
from datetime import date, timedelta
import re

_MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
_NAMED_MONTH = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+((?:19|20)\d{2})\b|"
    r"\b((?:19|20)\d{2})-(0[1-9]|1[0-2])\b(?!-\d)",
    re.IGNORECASE,
)
_EXPLICIT_DAY = re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b|\b(?:before|through|until|starting|first|last|days?)\b",
                           re.IGNORECASE)


def calendar_cohorts(question: str) -> set[date]:
    if _EXPLICIT_DAY.search(question):
        return set()
    return {
        date(int(match[2] or match[3]), _MONTHS[match[1].lower()] if match[1] else int(match[4]), 1)
        for match in _NAMED_MONTH.finditer(question)
    }


def repair_month_end(start: date | None, end: date | None, months: set[date]) -> date | None:
    if start in months and end == start.replace(day=calendar.monthrange(start.year, start.month)[1]):
        return end + timedelta(days=1)
    return end
