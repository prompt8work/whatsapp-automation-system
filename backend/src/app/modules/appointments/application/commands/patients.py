"""Patients and their cases."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.modules.appointments.application.dto import CaseDTO, PatientDTO
from app.modules.appointments.application.ports import PatientContacts
from app.modules.appointments.application.unit_of_work import AppointmentsUnitOfWork
from app.modules.appointments.domain.errors import CaseClosedError
from app.modules.appointments.domain.patient import Patient
from app.modules.appointments.domain.repositories import AppointmentFilter
from app.modules.appointments.domain.status import ACTIVE
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId


@dataclass(frozen=True)
class RegisterPatientCommand:
    tenant_id: TenantId
    contact_id: UUID
    full_name: str
    actor: Actor


class RegisterPatient:
    """A new patient profile under a contact - the first one, or "Someone new" (R4)."""

    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        self._uow, self._clock, self._ids = uow, clock, ids

    async def __call__(self, cmd: RegisterPatientCommand) -> PatientDTO:
        patient = Patient.register(
            id=self._ids.new_id(),
            tenant_id=cmd.tenant_id,
            contact_id=cmd.contact_id,
            full_name=cmd.full_name,
            actor=cmd.actor,
            at=self._clock.now(),
        )
        async with self._uow as uow:
            await uow.patients.add(patient)
            await uow.commit()
        return PatientDTO.from_domain(patient)


@dataclass(frozen=True)
class RegisterPatientForPhoneCommand:
    tenant_id: TenantId
    phone: str
    full_name: str
    actor: Actor


class RegisterPatientForPhone:
    """Staff registering a walk-in / phone caller: find or create the contact, then the patient."""

    def __init__(self, contacts: PatientContacts, register: RegisterPatient) -> None:
        self._contacts, self._register = contacts, register

    async def __call__(self, cmd: RegisterPatientForPhoneCommand) -> PatientDTO:
        contact_id = await self._contacts.contact_for_phone(cmd.tenant_id, cmd.phone)
        return await self._register(
            RegisterPatientCommand(cmd.tenant_id, contact_id, cmd.full_name, cmd.actor)
        )


@dataclass(frozen=True)
class RenamePatientCommand:
    patient_id: UUID
    full_name: str
    actor: Actor


class RenamePatient:
    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: RenamePatientCommand) -> PatientDTO:
        async with self._uow as uow:
            patient = await uow.patients.get(cmd.patient_id)
            patient.rename(cmd.full_name, actor=cmd.actor, at=self._clock.now())
            await uow.patients.save(patient)
            await uow.commit()
        return PatientDTO.from_domain(patient)


@dataclass(frozen=True)
class CaseCommand:
    case_id: UUID
    actor: Actor
    note: str = ""


class CloseCase:
    """Staff close a treatment episode (AP-10.2/10.3). Starts the 60-day retention clock."""

    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: CaseCommand) -> CaseDTO:
        async with self._uow as uow:
            case = await uow.cases.get(cmd.case_id)
            active = await uow.appointments.search(
                AppointmentFilter(case_id=case.id, statuses=ACTIVE)
            )
            case.close(
                active_appointments=len(active),
                note=cmd.note,
                actor=cmd.actor,
                at=self._clock.now(),
            )
            await uow.cases.save(case)
            await uow.commit()
        return CaseDTO.from_domain(case)


class ReopenCase:
    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: CaseCommand) -> CaseDTO:
        async with self._uow as uow:
            case = await uow.cases.get(cmd.case_id)
            open_case = await uow.cases.open_case_of(case.patient_id)
            if open_case is not None and open_case.id != case.id:
                raise CaseClosedError("This patient already has an open case")
            case.reopen(actor=cmd.actor, at=self._clock.now())
            await uow.cases.save(case)
            await uow.commit()
        return CaseDTO.from_domain(case)


@dataclass(frozen=True)
class LegalHoldCommand:
    case_id: UUID
    hold: bool
    actor: Actor


class SetLegalHold:
    def __init__(self, uow: AppointmentsUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, cmd: LegalHoldCommand) -> CaseDTO:
        async with self._uow as uow:
            case = await uow.cases.get(cmd.case_id)
            case.set_legal_hold(cmd.hold)
            await uow.cases.save(case)
            await uow.commit()
        return CaseDTO.from_domain(case)
