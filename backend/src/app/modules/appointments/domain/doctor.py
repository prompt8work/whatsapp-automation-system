"""Doctor: who can be booked, where, for how long, and when they work."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from uuid import UUID

from app.modules.appointments.domain.errors import InvalidDoctorError, InvalidScheduleError
from app.modules.appointments.domain.events import DoctorChanged
from app.modules.appointments.domain.values import TimeOff, WorkingHours
from app.shared.kernel.actor import Actor
from app.shared.kernel.entity import TenantAggregateRoot
from app.shared.kernel.ids import TenantId

ALLOWED_SLOT_MINUTES = (5, 10, 15, 20, 30, 45, 60, 90, 120)


def _valid_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > 120:
        raise InvalidDoctorError("Name must be 1-120 characters")
    return cleaned


def _valid_slot(minutes: int) -> int:
    if minutes not in ALLOWED_SLOT_MINUTES:
        raise InvalidDoctorError(f"Slot length must be one of {ALLOWED_SLOT_MINUTES} minutes")
    return minutes


@dataclass(kw_only=True, eq=False)
class Doctor(TenantAggregateRoot):
    location_id: UUID
    name: str
    specialty: str
    slot_minutes: int
    created_at: datetime
    user_id: UUID | None = None  # the doctor's dashboard login, if any ("my appointments")
    is_active: bool = True
    working_hours: list[WorkingHours] = field(default_factory=list)
    time_off: list[TimeOff] = field(default_factory=list)

    @classmethod
    def add(
        cls,
        *,
        id: UUID,
        tenant_id: TenantId,
        location_id: UUID,
        name: str,
        specialty: str,
        slot_minutes: int,
        actor: Actor,
        at: datetime,
        user_id: UUID | None = None,
    ) -> Doctor:
        doctor = cls(
            id=id,
            tenant_id=tenant_id,
            location_id=location_id,
            name=_valid_name(name),
            specialty=" ".join(specialty.split())[:80],
            slot_minutes=_valid_slot(slot_minutes),
            created_at=at,
            user_id=user_id,
        )
        doctor.record(DoctorChanged(occurred_at=at, doctor_id=id, what="added", actor=actor))
        return doctor

    def update(
        self,
        *,
        actor: Actor,
        at: datetime,
        name: str | None = None,
        specialty: str | None = None,
        slot_minutes: int | None = None,
        location_id: UUID | None = None,
        is_active: bool | None = None,
        user_id: UUID | None = None,
    ) -> None:
        if name is not None:
            self.name = _valid_name(name)
        if specialty is not None:
            self.specialty = " ".join(specialty.split())[:80]
        if slot_minutes is not None:
            self.slot_minutes = _valid_slot(slot_minutes)
        if location_id is not None:
            self.location_id = location_id
        if is_active is not None:
            self.is_active = is_active
        if user_id is not None:
            self.user_id = user_id
        self.record(DoctorChanged(occurred_at=at, doctor_id=self.id, what="updated", actor=actor))

    def set_working_hours(self, hours: list[WorkingHours], *, actor: Actor, at: datetime) -> None:
        ordered = sorted(hours, key=lambda h: (h.weekday, h.start))
        for before, after in pairwise(ordered):
            if before.weekday == after.weekday and after.start < before.end:
                raise InvalidScheduleError("Working hours on the same day overlap")
        self.working_hours = ordered
        self.record(
            DoctorChanged(occurred_at=at, doctor_id=self.id, what="working_hours", actor=actor)
        )

    def add_time_off(self, time_off: TimeOff, *, actor: Actor, at: datetime) -> None:
        self.time_off = sorted([*self.time_off, time_off], key=lambda t: t.start)
        self.record(DoctorChanged(occurred_at=at, doctor_id=self.id, what="time_off", actor=actor))

    def remove_time_off(self, time_off_id: UUID, *, actor: Actor, at: datetime) -> None:
        self.time_off = [t for t in self.time_off if t.id != time_off_id]
        self.record(DoctorChanged(occurred_at=at, doctor_id=self.id, what="time_off", actor=actor))

    def hours_on(self, weekday: int) -> list[WorkingHours]:
        return [h for h in self.working_hours if h.weekday == weekday]
