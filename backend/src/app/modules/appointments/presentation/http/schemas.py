"""Request/response shapes of the appointments API (they become the dashboard's TS types)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from app.modules.appointments.application.dto import (
    AppointmentDetailDTO,
    AppointmentDTO,
    CaseDTO,
    DeletionRequestDTO,
    DoctorDTO,
    PatientDTO,
    SlotDTO,
)


# ------------------------------------------------------------------ settings (AP-7.7)
class BookingFieldSchema(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(min_length=1, max_length=80)
    type: Literal["text", "number", "date", "choice"] = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=10)


class AppointmentSettings(BaseModel):
    """The clinic's booking rules. Stored as the tenant's `appointments` module settings."""

    approval_required: bool = True
    reason_required: bool = True
    request_expiry_hours: float = Field(default=4, gt=0, le=168)
    change_cutoff_hours: float = Field(default=2, ge=0, le=72)
    min_notice_minutes: int = Field(default=60, ge=0, le=7 * 24 * 60)
    horizon_days: int = Field(default=30, ge=1, le=365)
    # Retention (PRD AP-10.7): closed cases deleted N days after closing (RT-1), open cases
    # N days after their last activity (RT-2).
    retention_closed_days: int = Field(default=60, ge=1, le=3650)
    retention_open_days: int = Field(default=365, ge=30, le=3650)
    booking_fields: list[BookingFieldSchema] = Field(default_factory=list, max_length=10)


# ------------------------------------------------------------------ doctors
class WorkingHoursSchema(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 = Monday")
    start: time
    end: time


class TimeOffSchema(BaseModel):
    id: UUID
    start: datetime
    end: datetime
    reason: str


class DoctorResponse(BaseModel):
    id: UUID
    location_id: UUID
    name: str
    specialty: str
    slot_minutes: int
    is_active: bool
    user_id: UUID | None
    working_hours: list[WorkingHoursSchema]
    time_off: list[TimeOffSchema]

    @classmethod
    def from_dto(cls, d: DoctorDTO) -> DoctorResponse:
        return cls(
            id=d.id,
            location_id=d.location_id,
            name=d.name,
            specialty=d.specialty,
            slot_minutes=d.slot_minutes,
            is_active=d.is_active,
            user_id=d.user_id,
            working_hours=[
                WorkingHoursSchema(weekday=h.weekday, start=h.start, end=h.end)
                for h in d.working_hours
            ],
            time_off=[
                TimeOffSchema(id=t.id, start=t.start, end=t.end, reason=t.reason)
                for t in d.time_off
            ],
        )


class AddDoctorRequest(BaseModel):
    location_id: UUID
    name: str = Field(min_length=1, max_length=120)
    specialty: str = Field(default="", max_length=80)
    slot_minutes: int = 15
    user_id: UUID | None = None


class UpdateDoctorRequest(BaseModel):
    location_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    specialty: str | None = Field(default=None, max_length=80)
    slot_minutes: int | None = None
    is_active: bool | None = None
    user_id: UUID | None = None


class AddTimeOffRequest(BaseModel):
    start: AwareDatetime
    end: AwareDatetime
    reason: str = Field(default="", max_length=200)


class SlotSchema(BaseModel):
    doctor_id: UUID
    start: datetime
    end: datetime

    @classmethod
    def from_dto(cls, s: SlotDTO) -> SlotSchema:
        return cls(doctor_id=s.doctor_id, start=s.start, end=s.end)


class SlotsResponse(BaseModel):
    date: date
    timezone: str
    slots: list[SlotSchema]


# ------------------------------------------------------------------ patients & cases
class RegisterPatientRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=20, examples=["+91 98765 43210"])
    full_name: str = Field(min_length=2, max_length=120)


class RenamePatientRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)


class PatientResponse(BaseModel):
    id: UUID
    contact_id: UUID
    full_name: str

    @classmethod
    def from_dto(cls, p: PatientDTO) -> PatientResponse:
        return cls(id=p.id, contact_id=p.contact_id, full_name=p.full_name)


class CaseResponse(BaseModel):
    id: UUID
    patient_id: UUID
    status: str
    opened_at: datetime
    closed_at: datetime | None
    last_activity_at: datetime
    closing_note: str
    legal_hold: bool
    deletes_at: datetime | None = None

    @classmethod
    def from_dto(cls, c: CaseDTO) -> CaseResponse:
        return cls(**vars(c))


class CloseCaseRequest(BaseModel):
    note: str = Field(default="", max_length=500)


class LegalHoldRequest(BaseModel):
    hold: bool


# ------------------------------------------------------------------ appointments
class AppointmentResponse(BaseModel):
    id: UUID
    reference: str
    status: str
    case_id: UUID
    patient_id: UUID
    patient_name: str
    doctor_name: str
    location_id: UUID
    slot: SlotSchema
    original_slot: SlotSchema
    was_rescheduled: bool
    pending_slot: SlotSchema | None
    reason: str
    fields: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_dto(cls, a: AppointmentDTO) -> AppointmentResponse:
        return cls(
            id=a.id,
            reference=a.reference,
            status=a.status,
            case_id=a.case_id,
            patient_id=a.patient_id,
            patient_name=a.patient_name,
            doctor_name=a.doctor_name,
            location_id=a.location_id,
            slot=SlotSchema.from_dto(a.slot),
            original_slot=SlotSchema.from_dto(a.original_slot),
            was_rescheduled=a.was_rescheduled,
            pending_slot=SlotSchema.from_dto(a.pending_slot) if a.pending_slot else None,
            reason=a.reason,
            fields=a.fields,
            created_at=a.created_at,
        )


class HistoryEntryResponse(BaseModel):
    event_type: str
    occurred_at: datetime
    actor: str
    channel: str
    data: dict[str, Any]


class AppointmentDetailResponse(BaseModel):
    appointment: AppointmentResponse
    phone: str
    history: list[HistoryEntryResponse]

    @classmethod
    def from_dto(cls, d: AppointmentDetailDTO) -> AppointmentDetailResponse:
        return cls(
            appointment=AppointmentResponse.from_dto(d.appointment),
            phone=d.phone,
            history=[HistoryEntryResponse(**vars(h)) for h in d.history],
        )


class BookRequest(BaseModel):
    patient_id: UUID
    doctor_id: UUID
    start: AwareDatetime
    reason: str | None = Field(default=None, max_length=500)
    fields: dict[str, Any] = Field(default_factory=dict)


class ReasonRequest(BaseModel):
    reason: str = Field(default="", max_length=300)


class RescheduleRequest(BaseModel):
    start: AwareDatetime
    doctor_id: UUID | None = None


class AttendanceRequest(BaseModel):
    attended: bool


class UpdateDetailsRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    fields: dict[str, Any] | None = None


# ------------------------------------------------------------------ deletion requests
class DeletionPatient(BaseModel):
    id: UUID
    name: str | None  # None once deleted


class DeletionRequestResponse(BaseModel):
    id: UUID
    contact_id: UUID
    patients: list[DeletionPatient]
    status: Literal["pending", "completed", "rejected"]
    requested_at: datetime
    answer_by: datetime
    decided_at: datetime | None
    rejection_reason: str
    deleted_counts: dict[str, int]

    @classmethod
    def from_dto(cls, d: DeletionRequestDTO) -> DeletionRequestResponse:
        return cls(
            id=d.id,
            contact_id=d.contact_id,
            patients=[DeletionPatient(id=pid, name=name) for pid, name in d.patients.items()],
            status=d.status,
            requested_at=d.requested_at,
            answer_by=d.answer_by,
            decided_at=d.decided_at,
            rejection_reason=d.rejection_reason,
            deleted_counts=d.deleted_counts,
        )


class RejectDeletionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
