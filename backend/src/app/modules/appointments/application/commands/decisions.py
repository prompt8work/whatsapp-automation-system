"""The clinic's decisions on requests (PRD §7.3) and the automatic expiry of unanswered ones."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.modules.appointments.application.dto import AppointmentDTO
from app.modules.appointments.application.ports import ClinicDirectory
from app.modules.appointments.application.unit_of_work import AppointmentsUnitOfWork
from app.modules.appointments.domain.policy import BookingPolicy
from app.modules.appointments.domain.repositories import HoldKind
from app.modules.appointments.domain.status import AppointmentStatus
from app.modules.appointments.domain.values import By
from app.shared.application.jobs import JobContext
from app.shared.kernel.actor import Actor, Channel
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import TenantId

EXPIRE_REQUEST_JOB = "appointments.expire_request"
EXPIRE_RESCHEDULE_JOB = "appointments.expire_reschedule"


@dataclass(frozen=True)
class DecisionCommand:
    appointment_id: UUID
    actor: Actor
    channel: Channel = Channel.DASHBOARD
    reason: str = ""


class ApproveRequest:
    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: DecisionCommand) -> AppointmentDTO:
        async with self._uow as uow:
            appointment = await uow.appointments.get(cmd.appointment_id)
            appointment.approve(By(cmd.actor, cmd.channel, self._clock.now()))
            await uow.appointments.save(appointment)
            await uow.commit()
        return AppointmentDTO.from_domain(appointment)


class DeclineRequest:
    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: DecisionCommand) -> AppointmentDTO:
        async with self._uow as uow:
            appointment = await uow.appointments.get(cmd.appointment_id)
            appointment.decline(cmd.reason, By(cmd.actor, cmd.channel, self._clock.now()))
            await uow.reservations.release(appointment.id, appointment.slot)
            await uow.appointments.save(appointment)
            await uow.commit()
        return AppointmentDTO.from_domain(appointment)


class ApproveReschedule:
    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: DecisionCommand) -> AppointmentDTO:
        async with self._uow as uow:
            appointment = await uow.appointments.get(cmd.appointment_id)
            given_up = appointment.approve_reschedule(By(cmd.actor, cmd.channel, self._clock.now()))
            await uow.reservations.release(appointment.id, given_up)
            await uow.reservations.promote(appointment.id, appointment.slot)
            await uow.appointments.save(appointment)
            await uow.commit()
        return AppointmentDTO.from_domain(appointment)


class DeclineReschedule:
    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: DecisionCommand) -> AppointmentDTO:
        async with self._uow as uow:
            appointment = await uow.appointments.get(cmd.appointment_id)
            held = appointment.decline_reschedule(
                cmd.reason, By(cmd.actor, cmd.channel, self._clock.now())
            )
            await uow.reservations.release(appointment.id, held)
            await uow.appointments.save(appointment)
            await uow.commit()
        return AppointmentDTO.from_domain(appointment)


class ExpireStale:
    """Job handler for both expiry jobs (AP-3.3). Idempotent: does nothing if staff already
    decided, or if the appointment changed since the job was scheduled."""

    def __init__(
        self,
        uow_for: Callable[[TenantId], AppointmentsUnitOfWork],
        clinic: ClinicDirectory,
        clock: Clock,
    ) -> None:
        self._uow_for, self._clinic, self._clock = uow_for, clinic, clock

    async def __call__(self, ctx: JobContext) -> None:
        assert ctx.tenant_id is not None
        now = self._clock.now()
        policy = BookingPolicy.from_settings(await self._clinic.settings(ctx.tenant_id))
        by = By(Actor.system(), Channel.SCHEDULER, now)
        async with self._uow_for(ctx.tenant_id) as uow:
            appointment = await uow.appointments.get(UUID(ctx.payload["appointment_id"]))
            if ctx.job_type == EXPIRE_REQUEST_JOB:
                if appointment.status is not AppointmentStatus.REQUESTED:
                    return
                appointment.expire(by)
                await uow.reservations.release(appointment.id, appointment.slot)
            else:
                pending = appointment.pending_slot
                if (
                    pending is None
                    or appointment.pending_since is None
                    or appointment.pending_since + policy.request_expiry > now
                ):
                    return
                appointment.decline_reschedule("Not answered in time", by)
                await uow.reservations.release(appointment.id, pending)
            await uow.appointments.save(appointment)
            await uow.commit()


__all__ = [
    "EXPIRE_REQUEST_JOB",
    "EXPIRE_RESCHEDULE_JOB",
    "ApproveRequest",
    "ApproveReschedule",
    "DecisionCommand",
    "DeclineRequest",
    "DeclineReschedule",
    "ExpireStale",
    "HoldKind",
]
