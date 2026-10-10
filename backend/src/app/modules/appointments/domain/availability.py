"""Free slots: a pure function of the doctor's schedule, what is already booked, and the clock
(PRD AP-2.3). Used both to SHOW slots and to VALIDATE a requested time - one source of truth.

Working hours are local wall-clock time at the doctor's location; slots come out in UTC.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.modules.appointments.domain.doctor import Doctor
from app.modules.appointments.domain.errors import SlotUnavailableError
from app.modules.appointments.domain.policy import BookingPolicy
from app.modules.appointments.domain.values import Slot

Busy = Sequence[tuple[datetime, datetime]]


def free_slots(
    doctor: Doctor,
    day: date,
    *,
    timezone: str,
    busy: Busy,
    now: datetime,
    policy: BookingPolicy,
) -> list[Slot]:
    """Bookable slots of `doctor` on local date `day`."""
    tz = ZoneInfo(timezone)
    today = now.astimezone(tz).date()
    if not doctor.is_active or day < today or day > today + timedelta(days=policy.horizon_days):
        return []
    earliest = now + policy.min_notice
    length = timedelta(minutes=doctor.slot_minutes)
    blocked = [*busy, *((t.start, t.end) for t in doctor.time_off)]

    slots: list[Slot] = []
    for hours in doctor.hours_on(day.weekday()):
        cursor = datetime.combine(day, hours.start, tz)
        block_end = datetime.combine(day, hours.end, tz)
        while cursor + length <= block_end:
            slot = Slot(
                doctor.id,
                cursor.astimezone(ZoneInfo("UTC")),
                (cursor + length).astimezone(ZoneInfo("UTC")),
            )
            if slot.start >= earliest and not any(slot.overlaps(s, e) for s, e in blocked):
                slots.append(slot)
            cursor += length
    return slots


def require_free_slot(
    doctor: Doctor,
    start: datetime,
    *,
    timezone: str,
    busy: Busy,
    now: datetime,
    policy: BookingPolicy,
) -> Slot:
    """The slot starting at `start`, or SlotUnavailableError (wrong time, taken, too soon ...)."""
    local_day = start.astimezone(ZoneInfo(timezone)).date()
    for slot in free_slots(doctor, local_day, timezone=timezone, busy=busy, now=now, policy=policy):
        if slot.start == start:
            return slot
    raise SlotUnavailableError("That time is not available")
