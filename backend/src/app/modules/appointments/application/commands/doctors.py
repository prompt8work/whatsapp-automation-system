"""Clinic set-up: doctors, weekly hours, time off (PRD AP-7.7). Admin/staff only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.appointments.application.dto import DoctorDTO
from app.modules.appointments.application.ports import ClinicDirectory
from app.modules.appointments.application.unit_of_work import AppointmentsUnitOfWork
from app.modules.appointments.domain.doctor import Doctor
from app.modules.appointments.domain.errors import InvalidScheduleError
from app.modules.appointments.domain.values import TimeOff, WorkingHours
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId


@dataclass(frozen=True)
class AddDoctorCommand:
    tenant_id: TenantId
    location_id: UUID
    name: str
    specialty: str
    slot_minutes: int
    actor: Actor
    user_id: UUID | None = None


class AddDoctor:
    def __init__(
        self, uow: AppointmentsUnitOfWork, clinic: ClinicDirectory, clock: Clock, ids: IdGenerator
    ) -> None:
        self._uow, self._clinic, self._clock, self._ids = uow, clinic, clock, ids

    async def __call__(self, cmd: AddDoctorCommand) -> DoctorDTO:
        await self._clinic.timezone(cmd.tenant_id, cmd.location_id)  # location must exist
        doctor = Doctor.add(
            id=self._ids.new_id(),
            tenant_id=cmd.tenant_id,
            location_id=cmd.location_id,
            name=cmd.name,
            specialty=cmd.specialty,
            slot_minutes=cmd.slot_minutes,
            user_id=cmd.user_id,
            actor=cmd.actor,
            at=self._clock.now(),
        )
        async with self._uow as uow:
            await uow.doctors.add(doctor)
            await uow.commit()
        return DoctorDTO.from_domain(doctor)


@dataclass(frozen=True)
class UpdateDoctorCommand:
    tenant_id: TenantId
    doctor_id: UUID
    actor: Actor
    name: str | None = None
    specialty: str | None = None
    slot_minutes: int | None = None
    location_id: UUID | None = None
    is_active: bool | None = None
    user_id: UUID | None = None


class UpdateDoctor:
    def __init__(self, uow: AppointmentsUnitOfWork, clinic: ClinicDirectory, clock: Clock) -> None:
        self._uow, self._clinic, self._clock = uow, clinic, clock

    async def __call__(self, cmd: UpdateDoctorCommand) -> DoctorDTO:
        if cmd.location_id is not None:
            await self._clinic.timezone(cmd.tenant_id, cmd.location_id)
        async with self._uow as uow:
            doctor = await uow.doctors.get(cmd.doctor_id)
            doctor.update(
                actor=cmd.actor,
                at=self._clock.now(),
                name=cmd.name,
                specialty=cmd.specialty,
                slot_minutes=cmd.slot_minutes,
                location_id=cmd.location_id,
                is_active=cmd.is_active,
                user_id=cmd.user_id,
            )
            await uow.doctors.save(doctor)
            await uow.commit()
        return DoctorDTO.from_domain(doctor)


@dataclass(frozen=True)
class SetWorkingHoursCommand:
    doctor_id: UUID
    hours: list[WorkingHours]
    actor: Actor


class SetWorkingHours:
    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: SetWorkingHoursCommand) -> DoctorDTO:
        async with self._uow as uow:
            doctor = await uow.doctors.get(cmd.doctor_id)
            doctor.set_working_hours(cmd.hours, actor=cmd.actor, at=self._clock.now())
            await uow.doctors.save(doctor)
            await uow.commit()
        return DoctorDTO.from_domain(doctor)


@dataclass(frozen=True)
class TimeOffCommand:
    doctor_id: UUID
    actor: Actor
    start: datetime | None = None  # add
    end: datetime | None = None
    reason: str = ""
    remove_id: UUID | None = None  # or remove


class ChangeTimeOff:
    """Existing appointments in the period are NOT cancelled - staff handle them (PRD §9)."""

    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        self._uow, self._clock, self._ids = uow, clock, ids

    async def __call__(self, cmd: TimeOffCommand) -> DoctorDTO:
        now = self._clock.now()
        async with self._uow as uow:
            doctor = await uow.doctors.get(cmd.doctor_id)
            if cmd.remove_id is not None:
                doctor.remove_time_off(cmd.remove_id, actor=cmd.actor, at=now)
            else:
                if cmd.start is None or cmd.end is None:
                    raise InvalidScheduleError("Time off needs a start and an end")
                doctor.add_time_off(
                    TimeOff(self._ids.new_id(), cmd.start, cmd.end, cmd.reason.strip()[:200]),
                    actor=cmd.actor,
                    at=now,
                )
            await uow.doctors.save(doctor)
            await uow.commit()
        return DoctorDTO.from_domain(doctor)
