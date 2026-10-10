"""Read-side use cases for the dashboard (PRD §7.7) and, in step 5, the WhatsApp bot."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.modules.appointments.application.dto import (
    AppointmentDetailDTO,
    AppointmentDTO,
    CaseDTO,
    DoctorDTO,
    PatientDTO,
    SlotDTO,
)
from app.modules.appointments.application.ports import ClinicDirectory, PatientContacts
from app.modules.appointments.application.unit_of_work import AppointmentsUnitOfWork
from app.modules.appointments.domain.appointment import Appointment
from app.modules.appointments.domain.availability import free_slots
from app.modules.appointments.domain.errors import AppointmentNotFoundError
from app.modules.appointments.domain.policy import BookingPolicy
from app.modules.appointments.domain.repositories import AppointmentFilter
from app.modules.appointments.domain.status import ACTIVE, AppointmentStatus
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import TenantId


async def _with_names(
    uow: AppointmentsUnitOfWork, items: list[Appointment]
) -> list[AppointmentDTO]:
    patients = await uow.patients.get_many({a.patient_id for a in items})
    doctors = {d.id: d.name for d in await uow.doctors.list()}
    return [
        AppointmentDTO.from_domain(
            a,
            patient_name=patients[a.patient_id].full_name if a.patient_id in patients else "",
            doctor_name=doctors.get(a.doctor_id, ""),
        )
        for a in items
    ]


@dataclass(frozen=True)
class SlotsQuery:
    tenant_id: TenantId
    doctor_id: UUID
    day: date  # local date at the doctor's location


@dataclass(frozen=True)
class SlotsResult:
    timezone: str
    slots: list[SlotDTO]


class FindFreeSlots:
    def __init__(self, uow: AppointmentsUnitOfWork, clinic: ClinicDirectory, clock: Clock) -> None:
        self._uow, self._clinic, self._clock = uow, clinic, clock

    async def __call__(self, query: SlotsQuery) -> SlotsResult:
        policy = BookingPolicy.from_settings(await self._clinic.settings(query.tenant_id))
        async with self._uow as uow:
            doctor = await uow.doctors.get(query.doctor_id)
            timezone = await self._clinic.timezone(query.tenant_id, doctor.location_id)
            # A local day is within [UTC midnight - 1 day, + 2 days) for every timezone.
            utc_midnight = datetime.combine(query.day, time(), UTC)
            busy = await uow.reservations.busy(
                doctor.id, utc_midnight - timedelta(days=1), utc_midnight + timedelta(days=2)
            )
        slots = free_slots(
            doctor, query.day, timezone=timezone, busy=busy, now=self._clock.now(), policy=policy
        )
        return SlotsResult(timezone, [SlotDTO.from_domain(s) for s in slots])


@dataclass(frozen=True)
class ListAppointmentsQuery:
    tenant_id: TenantId
    on: date | None = None  # a day in the CLINIC's timezone (overrides start_from/start_to)
    start_from: datetime | None = None
    start_to: datetime | None = None
    doctor_id: UUID | None = None
    patient_id: UUID | None = None
    statuses: Collection[AppointmentStatus] = ()
    only_for_user: UUID | None = None  # set when the caller may only see their OWN appointments
    limit: int = 200


class ListAppointments:
    """Doctors with only `appointment.read` see their own appointments (PRD AP-7.2)."""

    def __init__(self, uow: AppointmentsUnitOfWork, clinic: ClinicDirectory) -> None:
        self._uow, self._clinic = uow, clinic

    async def __call__(self, query: ListAppointmentsQuery) -> list[AppointmentDTO]:
        start_from, start_to = query.start_from, query.start_to
        if query.on is not None:  # local midnight to midnight, as UTC instants
            tz = ZoneInfo(await self._clinic.tenant_timezone(query.tenant_id))
            start_from = datetime.combine(query.on, time(), tz).astimezone(UTC)
            start_to = datetime.combine(query.on + timedelta(days=1), time(), tz).astimezone(UTC)
        async with self._uow as uow:
            doctor_id = query.doctor_id
            if query.only_for_user is not None:
                own = await uow.doctors.find_by_user(query.only_for_user)
                if own is None or (doctor_id is not None and doctor_id != own.id):
                    return []
                doctor_id = own.id
            found = await uow.appointments.search(
                AppointmentFilter(
                    start_from=start_from,
                    start_to=start_to,
                    doctor_id=doctor_id,
                    patient_id=query.patient_id,
                    statuses=query.statuses,
                    limit=max(1, min(query.limit, 500)),
                )
            )
            return await _with_names(uow, found)


class ListRequests:
    """The approval queue (PRD AP-3.1): new requests + pending reschedules, oldest first."""

    def __init__(self, uow: AppointmentsUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self) -> list[AppointmentDTO]:
        async with self._uow as uow:
            new = await uow.appointments.search(
                AppointmentFilter(statuses={AppointmentStatus.REQUESTED})
            )
            moves = await uow.appointments.search(AppointmentFilter(pending_change_only=True))
            items = sorted(
                {a.id: a for a in [*new, *moves]}.values(),
                key=lambda a: a.pending_since or a.created_at,
            )
            return await _with_names(uow, items)


@dataclass(frozen=True)
class DetailQuery:
    tenant_id: TenantId
    appointment_id: UUID
    actor: Actor
    only_for_user: UUID | None = None


class GetAppointmentDetail:
    """Everything the doctor needs on one screen, including the full history (AP-7.3/7.4).
    Reading the phone number is audited by the contacts module."""

    def __init__(self, uow: AppointmentsUnitOfWork, contacts: PatientContacts) -> None:
        self._uow, self._contacts = uow, contacts

    async def __call__(self, query: DetailQuery) -> AppointmentDetailDTO:
        async with self._uow as uow:
            appointment = await uow.appointments.get(query.appointment_id)
            if query.only_for_user is not None:
                own = await uow.doctors.find_by_user(query.only_for_user)
                if own is None or own.id != appointment.doctor_id:
                    raise AppointmentNotFoundError()  # not "forbidden": do not reveal it exists
            [dto] = await _with_names(uow, [appointment])
            history = await uow.history.for_appointment(appointment.id)
        phone = await self._contacts.phone(query.tenant_id, appointment.contact_id, query.actor)
        return AppointmentDetailDTO(dto, phone, history)


class ListDoctors:
    def __init__(self, uow: AppointmentsUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, active_only: bool = False) -> list[DoctorDTO]:
        async with self._uow as uow:
            doctors = await uow.doctors.list(active_only=active_only)
        return [DoctorDTO.from_domain(d) for d in sorted(doctors, key=lambda d: d.name)]


class PatientsOfContact:
    """R4: everyone this WhatsApp number books for."""

    def __init__(self, uow: AppointmentsUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, contact_id: UUID) -> list[PatientDTO]:
        async with self._uow as uow:
            patients = await uow.patients.for_contact(contact_id)
        return [PatientDTO.from_domain(p) for p in sorted(patients, key=lambda p: p.created_at)]


class UpcomingForContact:
    """R2/R5: the contact's active appointments, soonest first."""

    def __init__(self, uow: AppointmentsUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, contact_id: UUID) -> list[AppointmentDTO]:
        async with self._uow as uow:
            found = await uow.appointments.search(
                AppointmentFilter(contact_id=contact_id, statuses=ACTIVE)
            )
            return await _with_names(uow, sorted(found, key=lambda a: a.slot.start))


class CasesOfPatient:
    def __init__(self, uow: AppointmentsUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, patient_id: UUID) -> list[CaseDTO]:
        async with self._uow as uow:
            cases = await uow.cases.for_patient(patient_id)
        return [
            CaseDTO.from_domain(c) for c in sorted(cases, key=lambda c: c.opened_at, reverse=True)
        ]
