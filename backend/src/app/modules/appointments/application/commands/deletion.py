"""Patients deleting their data on request (PRD AP-10.8-10.13).

RequestDeletion   the bot, after the patient confirmed: creates the PENDING request.
RejectDeletion    staff, with a reason the patient is told.
ApproveDeletion   staff: cancel active appointments (freeing the slots), purge every case and
                  the patient - the same purge as retention RT-1 - write the deletion records,
                  complete the request (-> the patient gets a confirmation on WhatsApp).
Payment records are never deleted (RT-7); the contact goes later under RT-4.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.modules.appointments.application.commands.changes import (
    CancelAppointment,
    CancelCommand,
)
from app.modules.appointments.application.dto import DeletionRequestDTO
from app.modules.appointments.application.ports import DeletionRecorder, PatientEraser
from app.modules.appointments.application.unit_of_work import AppointmentsUnitOfWork
from app.modules.appointments.domain.deletion_request import DeletionRequest, DeletionStatus
from app.modules.appointments.domain.errors import DeletionBlockedError, InvalidPatientError
from app.modules.appointments.domain.repositories import AppointmentFilter
from app.modules.appointments.domain.status import ACTIVE
from app.shared.application.retention import PurgeTarget
from app.shared.kernel.actor import Actor, Channel
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId

PURGER_KEY = "appointments.cases"
REQUEST_RULE = "AP-10.11"


async def _dto(uow: AppointmentsUnitOfWork, request: DeletionRequest) -> DeletionRequestDTO:
    names = await uow.patients.get_many(request.patient_ids)
    return DeletionRequestDTO.from_domain(request, {pid: p.full_name for pid, p in names.items()})


@dataclass(frozen=True)
class RequestDeletionCommand:
    tenant_id: TenantId
    contact_id: UUID
    patient_ids: tuple[UUID, ...]  # of this contact (AP-10.12)


class RequestDeletion:
    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        self._uow, self._clock, self._ids = uow, clock, ids

    async def __call__(self, cmd: RequestDeletionCommand) -> DeletionRequestDTO:
        async with self._uow as uow:
            existing = await uow.deletion_requests.pending_for_contact(cmd.contact_id)
            if existing is not None:  # asked twice: one request is enough
                return await _dto(uow, existing)
            own = {p.id for p in await uow.patients.for_contact(cmd.contact_id)}
            if not cmd.patient_ids or not set(cmd.patient_ids) <= own:
                raise InvalidPatientError("Choose patients registered from this number")
            request = DeletionRequest.create(
                id=self._ids.new_id(),
                tenant_id=cmd.tenant_id,
                contact_id=cmd.contact_id,
                patient_ids=cmd.patient_ids,
                at=self._clock.now(),
            )
            await uow.deletion_requests.add(request)
            await uow.commit()
            return await _dto(uow, request)


class PendingDeletionOf:
    """The bot: has this number already asked? (then it does not ask again)."""

    def __init__(self, uow: AppointmentsUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, contact_id: UUID) -> bool:
        async with self._uow as uow:
            return await uow.deletion_requests.pending_for_contact(contact_id) is not None


class ListDeletionRequests:
    def __init__(self, uow: AppointmentsUnitOfWork) -> None:
        self._uow = uow

    async def __call__(
        self, status: DeletionStatus | None = None, limit: int = 100
    ) -> list[DeletionRequestDTO]:
        async with self._uow as uow:
            return [await _dto(uow, r) for r in await uow.deletion_requests.list(status, limit)]


@dataclass(frozen=True)
class DecideDeletionCommand:
    tenant_id: TenantId
    request_id: UUID
    actor: Actor
    reason: str = ""  # required to reject


class RejectDeletion:
    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: DecideDeletionCommand) -> DeletionRequestDTO:
        async with self._uow as uow:
            request = await uow.deletion_requests.get(cmd.request_id)
            request.reject(reason=cmd.reason, actor=cmd.actor, at=self._clock.now())
            await uow.deletion_requests.save(request)
            await uow.commit()
            return await _dto(uow, request)


class ApproveDeletion:
    def __init__(
        self,
        uow: AppointmentsUnitOfWork,
        cancel: CancelAppointment,
        eraser: PatientEraser,
        record: DeletionRecorder,
        clock: Clock,
    ) -> None:
        self._uow, self._cancel, self._eraser = uow, cancel, eraser
        self._record, self._clock = record, clock

    async def __call__(self, cmd: DecideDeletionCommand) -> DeletionRequestDTO:
        async with self._uow as uow:
            request = await uow.deletion_requests.get(cmd.request_id)
            request.ensure_pending()
            active: list[UUID] = []
            for patient_id in request.patient_ids:
                if any(c.legal_hold for c in await uow.cases.for_patient(patient_id)):
                    raise DeletionBlockedError(
                        "A case of this patient is on legal hold - lift it or reject the request"
                    )
                found = await uow.appointments.search(
                    AppointmentFilter(patient_id=patient_id, statuses=ACTIVE)
                )
                active += [a.id for a in found]

        for appointment_id in active:  # frees the slots; patient is told in the confirmation
            await self._cancel(
                CancelCommand(
                    cmd.tenant_id,
                    appointment_id,
                    cmd.actor,
                    Channel.DASHBOARD,
                    "Deleted at the patient's request",
                )
            )

        counts: dict[str, int] = {"cancelled_appointments": len(active)}
        for patient_id in request.patient_ids:
            result = await self._eraser.purge_patient(cmd.tenant_id, patient_id)
            target = PurgeTarget("patient", patient_id, REQUEST_RULE, self._clock.now())
            await self._record(cmd.tenant_id, PURGER_KEY, target, result)
            for key, n in result.counts.items():
                counts[key] = counts.get(key, 0) + n

        async with self._uow as uow:
            request = await uow.deletion_requests.get(cmd.request_id)
            request.complete(counts=counts, actor=cmd.actor, at=self._clock.now())
            await uow.deletion_requests.save(request)
            await uow.commit()
            return await _dto(uow, request)
