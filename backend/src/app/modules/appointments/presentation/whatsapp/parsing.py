"""Understanding typed dates and times (rule-based, PRD OQ-2; an LLM parser can replace this
behind the same functions in Phase 2). Buttons/lists are the main path; this is the fallback
for people who type "tomorrow" or "3 pm" instead of tapping."""

from __future__ import annotations

import re
from datetime import date, time, timedelta

_WEEKDAYS = {
    name: i
    for i, names in enumerate(
        [
            ("monday", "mon"),
            ("tuesday", "tue", "tues"),
            ("wednesday", "wed"),
            ("thursday", "thu", "thur", "thurs"),
            ("friday", "fri"),
            ("saturday", "sat"),
            ("sunday", "sun"),
        ]
    )
    for name in names
}
_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}


def parse_day(text: str, today: date) -> date | None:
    """'today', 'tomorrow', 'friday' (next one, today counts), '12 oct', 'oct 12', '12/10',
    '12-10-2026'. Day-first numeric dates, as written in India."""
    t = " ".join(text.lower().replace(",", " ").split())
    t = re.sub(r"\b(on|this|next|the)\b", "", t).strip()
    if t in {"today", "aaj"}:
        return today
    if t in {"tomorrow", "tmrw", "tmr", "kal"}:
        return today + timedelta(days=1)
    if t in {"day after tomorrow", "parso"}:
        return today + timedelta(days=2)
    if t in _WEEKDAYS:
        return today + timedelta(days=(_WEEKDAYS[t] - today.weekday()) % 7)

    numeric = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?", t)
    if numeric:
        day, month, year = int(numeric[1]), int(numeric[2]), numeric[3]
        return _build(day, month, int(year) if year else None, today)

    words = re.fullmatch(
        r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)(?:\s+(\d{4}))?|([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?",
        t,
    )
    if words:
        if words[1]:
            day, month_name, year = int(words[1]), words[2], words[3]
        else:
            day, month_name, year = int(words[5]), words[4], words[6]
        if month_name in _MONTHS:
            return _build(day, _MONTHS[month_name], int(year) if year else None, today)
    return None


def _build(day: int, month: int, year: int | None, today: date) -> date | None:
    if year is not None and year < 100:
        year += 2000
    try:
        candidate = date(year or today.year, month, day)
    except ValueError:
        return None
    if year is None and candidate < today:  # "12 jan" in December means next year
        try:
            candidate = date(today.year + 1, month, day)
        except ValueError:
            return None
    return candidate


def parse_time(text: str) -> time | None:
    """'3 pm', '3pm', '3:30 pm', '15:00', '15.30', 'noon'."""
    t = text.lower().replace(" ", "")
    if t in {"noon", "12noon"}:
        return time(12)
    match = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?(am|pm)?", t)
    if not match:
        return None
    hour, minute, meridiem = int(match[1]), int(match[2] or 0), match[3]
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    elif meridiem is None and 1 <= hour <= 7:
        hour += 12  # "3" at a clinic almost always means 3 pm
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return time(hour, minute)
