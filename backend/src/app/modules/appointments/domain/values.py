"""Small value objects used across the appointments domain."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from uuid import UUID

from app.modules.appointments.domain.errors import InvalidScheduleError
from app.shared.kernel.actor import Actor, Channel

# Crockford base32 without I, L, O, U: easy to read out over the phone.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_reference() -> str:
    """Short human reference, e.g. "APT-7K3Q" (PRD FR-1.6). Unique per tenant: the repository
    retries with a new one in the rare case of a clash."""
    return "APT-" + "".join(secrets.choice(_ALPHABET) for _ in range(4))


@dataclass(frozen=True)
class By:
    """Who changed something, through which channel, when - recorded on every event (AP-8.2)."""

    actor: Actor
    channel: Channel
    at: datetime


@dataclass(frozen=True)
class Slot:
    """A doctor's time range, always UTC."""

    doctor_id: UUID
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end <= self.start:
            raise InvalidScheduleError("A slot needs a timezone-aware start before its end")

    def overlaps(self, start: datetime, end: datetime) -> bool:
        return self.start < end and start < self.end

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


@dataclass(frozen=True)
class WorkingHours:
    """One weekly block in the location's local time, e.g. Mon 09:00-13:00."""

    weekday: int  # 0 = Monday ... 6 = Sunday
    start: time
    end: time

    def __post_init__(self) -> None:
        if not 0 <= self.weekday <= 6:
            raise InvalidScheduleError("weekday must be 0 (Monday) to 6 (Sunday)")
        if self.end <= self.start:
            raise InvalidScheduleError("Working hours must end after they start")


@dataclass(frozen=True)
class TimeOff:
    """Leave, a conference, a blocked afternoon (UTC)."""

    id: UUID
    start: datetime
    end: datetime
    reason: str = ""

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end <= self.start:
            raise InvalidScheduleError("Time off needs a timezone-aware start before its end")
