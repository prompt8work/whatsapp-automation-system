"""Show UTC times the way patients read them - in the clinic's timezone, e.g.
"Fri 12 Oct, 3:00 PM"."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


def local(dt: datetime, timezone: str) -> datetime:
    return dt.astimezone(ZoneInfo(timezone))


def clock(dt: datetime, timezone: str) -> str:
    """3:00 PM"""
    value = local(dt, timezone)
    return f"{value.hour % 12 or 12}:{value.minute:02d} {'AM' if value.hour < 12 else 'PM'}"


def day_label(day: date) -> str:
    """Fri 12 Oct"""
    return f"{day:%a} {day.day} {day:%b}"


def when(dt: datetime, timezone: str) -> str:
    """Fri 12 Oct, 3:00 PM"""
    return f"{day_label(local(dt, timezone).date())}, {clock(dt, timezone)}"
