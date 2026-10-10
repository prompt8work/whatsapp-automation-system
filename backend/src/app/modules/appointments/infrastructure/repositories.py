"""SQL repositories for the appointments module. RLS restricts every query to the tenant."""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, time
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, RowMapping, and_, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.appointments.domain.appointment import Appointment
from app.modules.appointments.domain.case import Case, CaseStatus
from app.modules.appointments.domain.doctor import Doctor
from app.modules.appointments.domain.errors import (
    AppointmentNotFoundError,
    CaseNotFoundError,
    DoctorNotFoundError,
    PatientNotFoundError,
    SlotUnavailableError,
)
from app.modules.appointments.domain.patient import Patient
from app.modules.appointments.domain.repositories import (
    AppointmentFilter,
    HistoryEntry,
    HoldKind,
)
from app.modules.appointments.domain.status import AppointmentStatus
from app.modules.appointments.domain.values import Slot, TimeOff, WorkingHours, new_reference
from app.modules.appointments.infrastructure.tables import (
    appointment_events,
    appointments,
    cases,
    doctors,
    patients,
    slot_reservations,
)
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.kernel.errors import ConcurrencyConflictError
from app.shared.kernel.ids import IdGenerator, TenantId


async def _versioned_update(
    session: AsyncSession, table: Any, entity_id: UUID, version: int, values: dict[str, Any]
) -> None:
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(table)
            .where(table.c.id == entity_id, table.c.version == version)
            .values(values | {"version": version + 1})
        ),
    )
    if result.rowcount != 1:
        raise ConcurrencyConflictError()


# ================================================================== doctors
def _doctor(r: RowMapping) -> Doctor:
    return Doctor(
        id=r["id"],
        tenant_id=TenantId(r["tenant_id"]),
        location_id=r["location_id"],
        name=r["name"],
        specialty=r["specialty"],
        slot_minutes=r["slot_minutes"],
        user_id=r["user_id"],
        is_active=r["is_active"],
        working_hours=[
            WorkingHours(h["weekday"], time.fromisoformat(h["start"]), time.fromisoformat(h["end"]))
            for h in r["working_hours"]
        ],
        time_off=[
            TimeOff(
                UUID(t["id"]),
                datetime.fromisoformat(t["start"]),
                datetime.fromisoformat(t["end"]),
                t.get("reason", ""),
            )
            for t in r["time_off"]
        ],
        created_at=r["created_at"],
        version=r["version"],
    )


def _doctor_row(d: Doctor) -> dict[str, Any]:
    return {
        "id": d.id,
        "tenant_id": d.tenant_id,
        "location_id": d.location_id,
        "name": d.name,
        "specialty": d.specialty,
        "slot_minutes": d.slot_minutes,
        "user_id": d.user_id,
        "is_active": d.is_active,
        "working_hours": [
            {"weekday": h.weekday, "start": h.start.isoformat(), "end": h.end.isoformat()}
            for h in d.working_hours
        ],
        "time_off": [
            {
                "id": str(t.id),
                "start": t.start.isoformat(),
                "end": t.end.isoformat(),
                "reason": t.reason,
            }
            for t in d.time_off
        ],
        "created_at": d.created_at,
        "version": d.version,
    }


class SqlDoctorRepository:
    def __init__(self, session: AsyncSession, uow: UnitOfWork) -> None:
        self._session, self._uow = session, uow

    async def get(self, doctor_id: UUID) -> Doctor:
        row = (
            (await self._session.execute(select(doctors).where(doctors.c.id == doctor_id)))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DoctorNotFoundError()
        doctor = _doctor(row)
        self._uow.track(doctor)
        return doctor

    async def list(self, *, active_only: bool = False) -> list[Doctor]:
        stmt = select(doctors)
        if active_only:
            stmt = stmt.where(doctors.c.is_active)
        return [_doctor(r) for r in (await self._session.execute(stmt)).mappings()]

    async def find_by_user(self, user_id: UUID) -> Doctor | None:
        row = (
            (await self._session.execute(select(doctors).where(doctors.c.user_id == user_id)))
            .mappings()
            .first()
        )
        return _doctor(row) if row else None

    async def add(self, doctor: Doctor) -> None:
        await self._session.execute(insert(doctors).values(_doctor_row(doctor)))
        self._uow.track(doctor)

    async def save(self, doctor: Doctor) -> None:
        await _versioned_update(
            self._session, doctors, doctor.id, doctor.version, _doctor_row(doctor)
        )
        doctor.version += 1
        self._uow.track(doctor)


# ================================================================== patients
def _patient(r: RowMapping) -> Patient:
    return Patient(
        id=r["id"],
        tenant_id=TenantId(r["tenant_id"]),
        contact_id=r["contact_id"],
        full_name=r["full_name"],
        created_at=r["created_at"],
        version=r["version"],
    )


class SqlPatientRepository:
    def __init__(self, session: AsyncSession, uow: UnitOfWork) -> None:
        self._session, self._uow = session, uow

    async def get(self, patient_id: UUID) -> Patient:
        row = (
            (await self._session.execute(select(patients).where(patients.c.id == patient_id)))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise PatientNotFoundError()
        patient = _patient(row)
        self._uow.track(patient)
        return patient

    async def get_many(self, patient_ids: Collection[UUID]) -> dict[UUID, Patient]:
        if not patient_ids:
            return {}
        rows = await self._session.execute(
            select(patients).where(patients.c.id.in_(list(patient_ids)))
        )
        return {r["id"]: _patient(r) for r in rows.mappings()}

    async def for_contact(self, contact_id: UUID) -> list[Patient]:
        rows = await self._session.execute(
            select(patients).where(patients.c.contact_id == contact_id)
        )
        return [_patient(r) for r in rows.mappings()]

    async def add(self, patient: Patient) -> None:
        await self._session.execute(
            insert(patients).values(
                id=patient.id,
                tenant_id=patient.tenant_id,
                contact_id=patient.contact_id,
                full_name=patient.full_name,
                created_at=patient.created_at,
                version=patient.version,
            )
        )
        self._uow.track(patient)

    async def save(self, patient: Patient) -> None:
        await _versioned_update(
            self._session, patients, patient.id, patient.version, {"full_name": patient.full_name}
        )
        patient.version += 1
        self._uow.track(patient)


# ================================================================== cases
def _case(r: RowMapping) -> Case:
    return Case(
        id=r["id"],
        tenant_id=TenantId(r["tenant_id"]),
        patient_id=r["patient_id"],
        status=CaseStatus(r["status"]),
        opened_at=r["opened_at"],
        last_activity_at=r["last_activity_at"],
        closed_at=r["closed_at"],
        closing_note=r["closing_note"],
        legal_hold=r["legal_hold"],
        version=r["version"],
    )


def _case_row(c: Case) -> dict[str, Any]:
    return {
        "id": c.id,
        "tenant_id": c.tenant_id,
        "patient_id": c.patient_id,
        "status": c.status.value,
        "opened_at": c.opened_at,
        "last_activity_at": c.last_activity_at,
        "closed_at": c.closed_at,
        "closing_note": c.closing_note,
        "legal_hold": c.legal_hold,
        "version": c.version,
    }


class SqlCaseRepository:
    def __init__(self, session: AsyncSession, uow: UnitOfWork) -> None:
        self._session, self._uow = session, uow

    async def _one(self, where: Any) -> Case | None:
        row = (await self._session.execute(select(cases).where(where))).mappings().one_or_none()
        if row is None:
            return None
        case = _case(row)
        self._uow.track(case)
        return case

    async def get(self, case_id: UUID) -> Case:
        case = await self._one(cases.c.id == case_id)
        if case is None:
            raise CaseNotFoundError()
        return case

    async def open_case_of(self, patient_id: UUID) -> Case | None:
        return await self._one(
            and_(cases.c.patient_id == patient_id, cases.c.status == CaseStatus.OPEN.value)
        )

    async def for_patient(self, patient_id: UUID) -> list[Case]:
        rows = await self._session.execute(select(cases).where(cases.c.patient_id == patient_id))
        return [_case(r) for r in rows.mappings()]

    async def add(self, case: Case) -> None:
        await self._session.execute(insert(cases).values(_case_row(case)))
        self._uow.track(case)

    async def save(self, case: Case) -> None:
        await _versioned_update(self._session, cases, case.id, case.version, _case_row(case))
        case.version += 1
        self._uow.track(case)


# ================================================================== appointments
def _appointment(r: RowMapping) -> Appointment:
    pending = (
        Slot(r["pending_doctor_id"], r["pending_start_at"], r["pending_end_at"])
        if r["pending_start_at"] is not None
        else None
    )
    return Appointment(
        id=r["id"],
        tenant_id=TenantId(r["tenant_id"]),
        reference=r["reference"],
        case_id=r["case_id"],
        patient_id=r["patient_id"],
        contact_id=r["contact_id"],
        location_id=r["location_id"],
        slot=Slot(r["doctor_id"], r["start_at"], r["end_at"]),
        original_slot=Slot(r["original_doctor_id"], r["original_start_at"], r["original_end_at"]),
        status=AppointmentStatus(r["status"]),
        reason=r["reason"],
        fields=dict(r["fields"]),
        pending_slot=pending,
        pending_since=r["pending_since"],
        created_at=r["created_at"],
        version=r["version"],
    )


def _appointment_row(a: Appointment) -> dict[str, Any]:
    p = a.pending_slot
    return {
        "id": a.id,
        "tenant_id": a.tenant_id,
        "reference": a.reference,
        "case_id": a.case_id,
        "patient_id": a.patient_id,
        "contact_id": a.contact_id,
        "location_id": a.location_id,
        "doctor_id": a.slot.doctor_id,
        "start_at": a.slot.start,
        "end_at": a.slot.end,
        "original_doctor_id": a.original_slot.doctor_id,
        "original_start_at": a.original_slot.start,
        "original_end_at": a.original_slot.end,
        "pending_doctor_id": p.doctor_id if p else None,
        "pending_start_at": p.start if p else None,
        "pending_end_at": p.end if p else None,
        "pending_since": a.pending_since,
        "status": a.status.value,
        "reason": a.reason,
        "fields": a.fields,
        "created_at": a.created_at,
        "version": a.version,
    }


class SqlAppointmentRepository:
    def __init__(self, session: AsyncSession, uow: UnitOfWork) -> None:
        self._session, self._uow = session, uow

    async def get(self, appointment_id: UUID) -> Appointment:
        row = (
            (
                await self._session.execute(
                    select(appointments).where(appointments.c.id == appointment_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise AppointmentNotFoundError()
        appointment = _appointment(row)
        self._uow.track(appointment)
        return appointment

    async def find_by_reference(self, reference: str) -> Appointment | None:
        row = (
            (
                await self._session.execute(
                    select(appointments).where(appointments.c.reference == reference.upper())
                )
            )
            .mappings()
            .one_or_none()
        )
        return _appointment(row) if row else None

    async def search(self, query: AppointmentFilter) -> list[Appointment]:
        c = appointments.c
        stmt = select(appointments)
        if query.start_from:
            stmt = stmt.where(c.start_at >= query.start_from)
        if query.start_to:
            stmt = stmt.where(c.start_at < query.start_to)
        for column, value in (
            (c.doctor_id, query.doctor_id),
            (c.patient_id, query.patient_id),
            (c.contact_id, query.contact_id),
            (c.case_id, query.case_id),
        ):
            if value is not None:
                stmt = stmt.where(column == value)
        if query.statuses:
            stmt = stmt.where(c.status.in_([s.value for s in query.statuses]))
        if query.pending_change_only:
            stmt = stmt.where(c.pending_start_at.isnot(None))
        stmt = stmt.order_by(c.start_at).limit(query.limit)
        return [_appointment(r) for r in (await self._session.execute(stmt)).mappings()]

    async def add(self, appointment: Appointment) -> None:
        for _ in range(5):
            try:
                async with self._session.begin_nested():
                    await self._session.execute(
                        insert(appointments).values(_appointment_row(appointment))
                    )
                break
            except IntegrityError as exc:
                if "uq_appointments_reference" not in str(exc.orig):
                    raise
                appointment.reassign_reference(new_reference())
        else:
            raise RuntimeError("Could not allocate a unique appointment reference")
        self._uow.track(appointment)

    async def save(self, appointment: Appointment) -> None:
        await _versioned_update(
            self._session,
            appointments,
            appointment.id,
            appointment.version,
            _appointment_row(appointment),
        )
        appointment.version += 1
        self._uow.track(appointment)


# ================================================================== reservations
class SqlSlotReservations:
    def __init__(self, session: AsyncSession, tenant_id: TenantId | None, ids: IdGenerator) -> None:
        self._session, self._tenant_id, self._ids = session, tenant_id, ids

    async def busy(
        self,
        doctor_id: UUID,
        start: datetime,
        end: datetime,
        *,
        exclude_appointment: UUID | None = None,
    ) -> list[tuple[datetime, datetime]]:
        c = slot_reservations.c
        stmt = select(c.start_at, c.end_at).where(
            c.doctor_id == doctor_id, c.active, c.start_at < end, c.end_at > start
        )
        if exclude_appointment is not None:
            stmt = stmt.where(c.appointment_id != exclude_appointment)
        return [(r.start_at, r.end_at) for r in await self._session.execute(stmt)]

    async def reserve(self, appointment_id: UUID, slot: Slot, kind: HoldKind) -> None:
        # Serialise every booking for this doctor until commit: two simultaneous requests for
        # the same time cannot both pass the overlap check below (PRD AC-8).
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"doctor:{slot.doctor_id}"},
        )
        if await self.busy(
            slot.doctor_id, slot.start, slot.end, exclude_appointment=appointment_id
        ):
            raise SlotUnavailableError("Sorry, that time was just taken")
        await self._session.execute(
            insert(slot_reservations).values(
                id=self._ids.new_id(),
                tenant_id=self._tenant_id,
                appointment_id=appointment_id,
                doctor_id=slot.doctor_id,
                kind=kind.value,
                start_at=slot.start,
                end_at=slot.end,
                active=True,
                created_at=text("now()"),
            )
        )

    async def release(self, appointment_id: UUID, slot: Slot) -> None:
        c = slot_reservations.c
        await self._session.execute(
            update(slot_reservations)
            .where(
                c.appointment_id == appointment_id,
                c.doctor_id == slot.doctor_id,
                c.start_at == slot.start,
                c.active,
            )
            .values(active=False)
        )

    async def promote(self, appointment_id: UUID, slot: Slot) -> None:
        c = slot_reservations.c
        await self._session.execute(
            update(slot_reservations)
            .where(
                c.appointment_id == appointment_id,
                c.doctor_id == slot.doctor_id,
                c.start_at == slot.start,
                c.active,
            )
            .values(kind=HoldKind.APPOINTMENT.value)
        )


# ================================================================== history
class SqlAppointmentHistory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def for_appointment(self, appointment_id: UUID) -> list[HistoryEntry]:
        e = appointment_events.c
        rows = await self._session.execute(
            select(appointment_events)
            .where(e.appointment_id == appointment_id)
            .order_by(e.occurred_at, e.id)
        )
        skip = {"appointment_id", "actor", "channel", "occurred_at", "event_id"}
        return [
            HistoryEntry(
                event_type=r["event_type"],
                occurred_at=r["occurred_at"],
                actor=r["actor"],
                channel=r["channel"],
                data={k: v for k, v in r["payload"].items() if k not in skip},
            )
            for r in rows.mappings()
        ]
