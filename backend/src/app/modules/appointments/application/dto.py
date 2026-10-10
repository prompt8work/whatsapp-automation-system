"""What use cases return. Times are UTC; the dashboard formats them in the clinic's timezone."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any
from uuid import UUID

from app.modules.appointments.domain.appointment import Appointment
from app.modules.appointments.domain.case import Case
from app.modules.appointments.domain.doctor import Doctor
from app.modules.appointments.domain.patient import Patient
from app.modules.appointments.domain.repositories import HistoryEntry
from app.modules.appointments.domain.values import Slot


@dataclass(frozen=True)
class SlotDTO:
    doctor_id: UUID
    start: datetime
    end: datetime

    @classmethod
    def from_domain(cls, slot: Slot) -> SlotDTO:
        return cls(slot.doctor_id, slot.start, slot.end)


@dataclass(frozen=True)
class WorkingHoursDTO:
    weekday: int
    start: time
    end: time


@dataclass(frozen=True)
class TimeOffDTO:
    id: UUID
    start: datetime
    end: datetime
    reason: str


@dataclass(frozen=True)
class DoctorDTO:
    id: UUID
    location_id: UUID
    name: str
    specialty: str
    slot_minutes: int
    is_active: bool
    user_id: UUID | None
    working_hours: list[WorkingHoursDTO]
    time_off: list[TimeOffDTO]

    @classmethod
    def from_domain(cls, d: Doctor) -> DoctorDTO:
        return cls(
            d.id,
            d.location_id,
            d.name,
            d.specialty,
            d.slot_minutes,
            d.is_active,
            d.user_id,
            [WorkingHoursDTO(h.weekday, h.start, h.end) for h in d.working_hours],
            [TimeOffDTO(t.id, t.start, t.end, t.reason) for t in d.time_off],
        )


@dataclass(frozen=True)
class PatientDTO:
    id: UUID
    contact_id: UUID
    full_name: str

    @classmethod
    def from_domain(cls, p: Patient) -> PatientDTO:
        return cls(p.id, p.contact_id, p.full_name)


@dataclass(frozen=True)
class CaseDTO:
    id: UUID
    patient_id: UUID
    status: str
    opened_at: datetime
    closed_at: datetime | None
    last_activity_at: datetime
    closing_note: str
    legal_hold: bool

    @classmethod
    def from_domain(cls, c: Case) -> CaseDTO:
        return cls(
            c.id,
            c.patient_id,
            c.status.value,
            c.opened_at,
            c.closed_at,
            c.last_activity_at,
            c.closing_note,
            c.legal_hold,
        )


@dataclass(frozen=True)
class AppointmentDTO:
    id: UUID
    reference: str
    status: str
    case_id: UUID
    patient_id: UUID
    contact_id: UUID
    location_id: UUID
    slot: SlotDTO
    original_slot: SlotDTO
    was_rescheduled: bool
    pending_slot: SlotDTO | None
    reason: str
    fields: dict[str, Any]
    created_at: datetime
    patient_name: str = ""
    doctor_name: str = ""

    @classmethod
    def from_domain(
        cls, a: Appointment, *, patient_name: str = "", doctor_name: str = ""
    ) -> AppointmentDTO:
        return cls(
            id=a.id,
            reference=a.reference,
            status=a.status.value,
            case_id=a.case_id,
            patient_id=a.patient_id,
            contact_id=a.contact_id,
            location_id=a.location_id,
            slot=SlotDTO.from_domain(a.slot),
            original_slot=SlotDTO.from_domain(a.original_slot),
            was_rescheduled=a.was_rescheduled,
            pending_slot=SlotDTO.from_domain(a.pending_slot) if a.pending_slot else None,
            reason=a.reason,
            fields=dict(a.fields),
            created_at=a.created_at,
            patient_name=patient_name,
            doctor_name=doctor_name,
        )


@dataclass(frozen=True)
class AppointmentDetailDTO:
    appointment: AppointmentDTO
    phone: str
    history: list[HistoryEntry] = field(default_factory=list)
