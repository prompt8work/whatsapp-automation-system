"""Module-level composition: adapters to the platform, use cases per tenant, routers,
job/event handlers. The only file here that picks concrete classes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import APIRouter

from app.modules.appointments.application.commands.booking import RequestAppointment
from app.modules.appointments.application.commands.changes import (
    CancelAppointment,
    RecordAttendance,
    RescheduleAppointment,
    UpdateAppointmentDetails,
)
from app.modules.appointments.application.commands.decisions import (
    ApproveRequest,
    ApproveReschedule,
    DeclineRequest,
    DeclineReschedule,
    ExpireStale,
)
from app.modules.appointments.application.commands.doctors import (
    AddDoctor,
    ChangeTimeOff,
    SetWorkingHours,
    UpdateDoctor,
)
from app.modules.appointments.application.commands.patients import (
    CloseCase,
    RegisterPatient,
    RegisterPatientForPhone,
    RenamePatient,
    ReopenCase,
    SetLegalHold,
)
from app.modules.appointments.application.handlers.expiry import ScheduleExpiry
from app.modules.appointments.application.queries.reads import (
    CasesOfPatient,
    FindFreeSlots,
    GetAppointmentDetail,
    ListAppointments,
    ListDoctors,
    ListRequests,
    PatientsOfContact,
    UpcomingForContact,
)
from app.modules.appointments.application.use_cases import AppointmentsUseCases
from app.modules.appointments.infrastructure.unit_of_work import SqlAppointmentsUnitOfWork
from app.modules.appointments.presentation.http.routers import SettingsStore, build_router
from app.platform.contacts.contracts import EnsureContactCommand, GetContactQuery
from app.platform.contacts.integration import contacts_for
from app.platform.tenancy.integration import tenancy_for
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.module import PlatformServices

MODULE_KEY = "appointments"


@dataclass(frozen=True)
class ClinicAdapter:
    """ClinicDirectory port on top of the tenancy facade."""

    services: PlatformServices

    async def timezone(self, tenant_id: TenantId, location_id: UUID) -> str:
        return await tenancy_for(self.services).location_timezone(tenant_id, location_id)

    async def settings(self, tenant_id: TenantId) -> dict[str, Any]:
        return await tenancy_for(self.services).module_settings(tenant_id, MODULE_KEY)


@dataclass(frozen=True)
class ContactsAdapter:
    """PatientContacts port on top of the contacts module (reads are audited there)."""

    services: PlatformServices

    async def phone(self, tenant_id: TenantId, contact_id: UUID, actor: Actor) -> str:
        contact = await contacts_for(self.services, tenant_id).get(
            GetContactQuery(tenant_id, actor, contact_id)
        )
        return contact.phone

    async def contact_for_phone(self, tenant_id: TenantId, phone: str) -> UUID:
        contact = await contacts_for(self.services, tenant_id).ensure(
            EnsureContactCommand(tenant_id, phone)
        )
        return contact.id


def uow_for(services: PlatformServices, tenant_id: TenantId) -> SqlAppointmentsUnitOfWork:
    return SqlAppointmentsUnitOfWork(services.session_factory, tenant_id, services.ids)


def use_cases_for(services: PlatformServices, tenant_id: TenantId) -> AppointmentsUseCases:
    """Used by the HTTP routers now and by the WhatsApp steps in build step 5."""
    uow = uow_for(services, tenant_id)
    clinic, contacts = ClinicAdapter(services), ContactsAdapter(services)
    clock, ids = services.clock, services.ids
    register = RegisterPatient(uow, clock, ids)
    return AppointmentsUseCases(
        add_doctor=AddDoctor(uow, clinic, clock, ids),
        update_doctor=UpdateDoctor(uow, clinic, clock),
        set_working_hours=SetWorkingHours(uow, clock),
        change_time_off=ChangeTimeOff(uow, clock, ids),
        list_doctors=ListDoctors(uow),
        find_free_slots=FindFreeSlots(uow, clinic, clock),
        register_patient=register,
        register_patient_for_phone=RegisterPatientForPhone(contacts, register),
        rename_patient=RenamePatient(uow, clock),
        patients_of_contact=PatientsOfContact(uow),
        cases_of_patient=CasesOfPatient(uow),
        close_case=CloseCase(uow, clock),
        reopen_case=ReopenCase(uow, clock),
        set_legal_hold=SetLegalHold(uow),
        request=RequestAppointment(uow, clinic, clock, ids),
        approve=ApproveRequest(uow, clock),
        decline=DeclineRequest(uow, clock),
        reschedule=RescheduleAppointment(uow, clinic, clock),
        approve_reschedule=ApproveReschedule(uow, clock),
        decline_reschedule=DeclineReschedule(uow, clock),
        cancel=CancelAppointment(uow, clinic, clock),
        record_attendance=RecordAttendance(uow, clock),
        update_details=UpdateAppointmentDetails(uow, clinic, clock),
        list_appointments=ListAppointments(uow),
        list_requests=ListRequests(uow),
        detail=GetAppointmentDetail(uow, contacts),
        upcoming_for_contact=UpcomingForContact(uow),
    )


def build_routers(services: PlatformServices) -> Sequence[APIRouter]:
    async def write(tenant_id: TenantId, settings: dict[str, Any], actor: Actor) -> None:
        await tenancy_for(services).update_module_settings(tenant_id, MODULE_KEY, settings, actor)

    store = SettingsStore(read=ClinicAdapter(services).settings, write=write)
    return [build_router(lambda tenant_id: use_cases_for(services, tenant_id), store)]


def expire_stale(services: PlatformServices) -> ExpireStale:
    return ExpireStale(lambda t: uow_for(services, t), ClinicAdapter(services), services.clock)


def schedule_expiry(services: PlatformServices) -> ScheduleExpiry:
    return ScheduleExpiry(services.jobs, ClinicAdapter(services))
