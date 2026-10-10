"""Changes to an existing appointment: reschedule (PRD §7.4), cancel, attendance, details."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.modules.appointments.application.commands.booking import find_slot
from app.modules.appointments.application.dto import AppointmentDTO
from app.modules.appointments.application.ports import ClinicDirectory
from app.modules.appointments.application.unit_of_work import AppointmentsUnitOfWork
from app.modules.appointments.domain.errors import SlotUnavailableError
from app.modules.appointments.domain.policy import BookingPolicy
from app.modules.appointments.domain.repositories import HoldKind
from app.modules.appointments.domain.status import AppointmentStatus
from app.modules.appointments.domain.values import By
from app.shared.kernel.actor import Actor, ActorKind, Channel
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import TenantId


@dataclass(frozen=True)
class RescheduleCommand:
    tenant_id: TenantId
    appointment_id: UUID
    new_start: datetime
    actor: Actor
    channel: Channel
    new_doctor_id: UUID | None = None  # None: same doctor


class RescheduleAppointment:
    """Patient + approval mode -> a reschedule REQUEST (new slot held, current one kept).
    Otherwise (staff, or no approval needed) -> moved straight away. Same id and reference."""

    def __init__(self, uow: AppointmentsUnitOfWork, clinic: ClinicDirectory, clock: Clock) -> None:
        self._uow, self._clinic, self._clock = uow, clinic, clock

    async def __call__(self, cmd: RescheduleCommand) -> AppointmentDTO:
        now = self._clock.now()
        policy = BookingPolicy.from_settings(await self._clinic.settings(cmd.tenant_id))
        by = By(cmd.actor, cmd.channel, now)
        is_staff = cmd.actor.kind is ActorKind.STAFF

        async with self._uow as uow:
            appointment = await uow.appointments.get(cmd.appointment_id)
            policy.ensure_can_change(appointment, cmd.actor, now)
            current_doctor = await uow.doctors.get(appointment.doctor_id)
            doctor = (
                await uow.doctors.get(cmd.new_doctor_id)
                if cmd.new_doctor_id and cmd.new_doctor_id != current_doctor.id
                else current_doctor
            )
            if not is_staff and doctor.specialty != current_doctor.specialty:
                raise SlotUnavailableError("You can only move to a doctor of the same specialty")
            new_slot = await find_slot(
                uow,
                self._clinic,
                cmd.tenant_id,
                doctor,
                cmd.new_start,
                now=now,
                policy=policy,
                exclude_appointment=appointment.id,
            )

            needs_approval = (
                policy.approval_required
                and not is_staff
                and appointment.status is not AppointmentStatus.REQUESTED
            )
            if needs_approval:
                if appointment.pending_slot is not None:  # replacing an earlier pending request
                    await uow.reservations.release(appointment.id, appointment.pending_slot)
                appointment.request_reschedule(new_slot, by)
                await uow.reservations.reserve(appointment.id, new_slot, HoldKind.RESCHEDULE)
            else:
                old = appointment.slot
                stale_hold = appointment.pending_slot
                appointment.reschedule(new_slot, by)
                for slot in (old, stale_hold):
                    if slot is not None:
                        await uow.reservations.release(appointment.id, slot)
                await uow.reservations.reserve(appointment.id, new_slot, HoldKind.APPOINTMENT)

            case = await uow.cases.get(appointment.case_id)
            case.touch(now)
            await uow.cases.save(case)
            await uow.appointments.save(appointment)
            await uow.commit()
        return AppointmentDTO.from_domain(appointment, doctor_name=doctor.name)


@dataclass(frozen=True)
class CancelCommand:
    tenant_id: TenantId
    appointment_id: UUID
    actor: Actor
    channel: Channel
    reason: str = ""


class CancelAppointment:
    def __init__(self, uow: AppointmentsUnitOfWork, clinic: ClinicDirectory, clock: Clock) -> None:
        self._uow, self._clinic, self._clock = uow, clinic, clock

    async def __call__(self, cmd: CancelCommand) -> AppointmentDTO:
        now = self._clock.now()
        policy = BookingPolicy.from_settings(await self._clinic.settings(cmd.tenant_id))
        async with self._uow as uow:
            appointment = await uow.appointments.get(cmd.appointment_id)
            if appointment.status is not AppointmentStatus.REQUESTED:
                policy.ensure_can_change(
                    appointment, cmd.actor, now
                )  # withdrawing a request is always fine
            for slot in appointment.cancel(cmd.reason, By(cmd.actor, cmd.channel, now)):
                await uow.reservations.release(appointment.id, slot)
            await uow.appointments.save(appointment)
            await uow.commit()
        return AppointmentDTO.from_domain(appointment)


@dataclass(frozen=True)
class AttendanceCommand:
    appointment_id: UUID
    attended: bool  # True: completed, False: no-show
    actor: Actor


class RecordAttendance:
    """Staff/doctor mark Completed or No-show (PRD AP-7.5) once the appointment has started."""

    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: AttendanceCommand) -> AppointmentDTO:
        by = By(cmd.actor, Channel.DASHBOARD, self._clock.now())
        async with self._uow as uow:
            appointment = await uow.appointments.get(cmd.appointment_id)
            if cmd.attended:
                appointment.complete(by)
            else:
                appointment.mark_no_show(by)
            await uow.reservations.release(appointment.id, appointment.slot)
            await uow.appointments.save(appointment)
            await uow.commit()
        return AppointmentDTO.from_domain(appointment)


@dataclass(frozen=True)
class UpdateDetailsCommand:
    tenant_id: TenantId
    appointment_id: UUID
    actor: Actor
    channel: Channel
    reason: str | None = None
    fields: dict[str, Any] | None = None


class UpdateAppointmentDetails:
    def __init__(self, uow: AppointmentsUnitOfWork, clinic: ClinicDirectory, clock: Clock) -> None:
        self._uow, self._clinic, self._clock = uow, clinic, clock

    async def __call__(self, cmd: UpdateDetailsCommand) -> AppointmentDTO:
        policy = BookingPolicy.from_settings(await self._clinic.settings(cmd.tenant_id))
        reason = policy.clean_reason(cmd.reason) if cmd.reason is not None else None
        fields = policy.clean_fields(cmd.fields) if cmd.fields is not None else None
        async with self._uow as uow:
            appointment = await uow.appointments.get(cmd.appointment_id)
            appointment.update_details(
                reason=reason, fields=fields, by=By(cmd.actor, cmd.channel, self._clock.now())
            )
            await uow.appointments.save(appointment)
            await uow.commit()
        return AppointmentDTO.from_domain(appointment)
