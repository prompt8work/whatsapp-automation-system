"""Book an appointment (PRD §7.2): validate -> find/open the case -> reserve the slot -> save.

The same use case serves the WhatsApp bot (actor = contact) and the dashboard (actor = staff).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from app.modules.appointments.application.dto import AppointmentDTO
from app.modules.appointments.application.ports import ClinicDirectory
from app.modules.appointments.application.unit_of_work import AppointmentsUnitOfWork
from app.modules.appointments.domain.appointment import Appointment
from app.modules.appointments.domain.availability import require_free_slot
from app.modules.appointments.domain.case import Case
from app.modules.appointments.domain.doctor import Doctor
from app.modules.appointments.domain.policy import BookingPolicy
from app.modules.appointments.domain.repositories import HoldKind
from app.modules.appointments.domain.values import By, Slot, new_reference
from app.shared.kernel.actor import Actor, Channel
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId


async def find_slot(
    uow: AppointmentsUnitOfWork,
    clinic: ClinicDirectory,
    tenant_id: TenantId,
    doctor: Doctor,
    start: datetime,
    *,
    now: datetime,
    policy: BookingPolicy,
    exclude_appointment: UUID | None = None,
) -> Slot:
    """The bookable slot starting at `start` - same rules as the slot picker."""
    timezone = await clinic.timezone(tenant_id, doctor.location_id)
    busy = await uow.reservations.busy(
        doctor.id,
        start - timedelta(days=1),
        start + timedelta(days=1),
        exclude_appointment=exclude_appointment,
    )
    return require_free_slot(doctor, start, timezone=timezone, busy=busy, now=now, policy=policy)


@dataclass(frozen=True)
class RequestAppointmentCommand:
    tenant_id: TenantId
    patient_id: UUID
    doctor_id: UUID
    start: datetime
    actor: Actor
    channel: Channel
    reason: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)


class RequestAppointment:
    def __init__(
        self, uow: AppointmentsUnitOfWork, clinic: ClinicDirectory, clock: Clock, ids: IdGenerator
    ) -> None:
        self._uow, self._clinic, self._clock, self._ids = uow, clinic, clock, ids

    async def __call__(self, cmd: RequestAppointmentCommand) -> AppointmentDTO:
        now = self._clock.now()
        policy = BookingPolicy.from_settings(await self._clinic.settings(cmd.tenant_id))
        reason = policy.clean_reason(cmd.reason)
        fields = policy.clean_fields(cmd.fields)
        by = By(cmd.actor, cmd.channel, now)

        async with self._uow as uow:
            patient = await uow.patients.get(cmd.patient_id)
            doctor = await uow.doctors.get(cmd.doctor_id)
            slot = await find_slot(
                uow, self._clinic, cmd.tenant_id, doctor, cmd.start, now=now, policy=policy
            )

            case = await uow.cases.open_case_of(patient.id)
            if case is None:
                case = Case.open(
                    id=self._ids.new_id(), tenant_id=cmd.tenant_id, patient_id=patient.id, at=now
                )
                await uow.cases.add(case)
            else:
                case.touch(now)
                await uow.cases.save(case)

            appointment = Appointment.book(
                id=self._ids.new_id(),
                tenant_id=cmd.tenant_id,
                reference=new_reference(),
                case_id=case.id,
                patient_id=patient.id,
                contact_id=patient.contact_id,
                location_id=doctor.location_id,
                slot=slot,
                reason=reason,
                fields=fields,
                needs_approval=policy.approval_required,
                by=by,
            )
            await uow.appointments.add(appointment)
            await uow.reservations.reserve(appointment.id, slot, HoldKind.APPOINTMENT)  # race guard
            await uow.commit()
        return AppointmentDTO.from_domain(
            appointment, patient_name=patient.full_name, doctor_name=doctor.name
        )
