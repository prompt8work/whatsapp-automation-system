"""Repository ports. All tenant-scoped (RLS)."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from app.modules.appointments.domain.appointment import Appointment
from app.modules.appointments.domain.case import Case
from app.modules.appointments.domain.deletion_request import DeletionRequest, DeletionStatus
from app.modules.appointments.domain.doctor import Doctor
from app.modules.appointments.domain.patient import Patient
from app.modules.appointments.domain.status import AppointmentStatus
from app.modules.appointments.domain.values import Slot


class DoctorRepository(Protocol):
    async def get(self, doctor_id: UUID) -> Doctor: ...

    async def list(self, *, active_only: bool = False) -> list[Doctor]: ...

    async def find_by_user(self, user_id: UUID) -> Doctor | None: ...

    async def add(self, doctor: Doctor) -> None: ...

    async def save(self, doctor: Doctor) -> None: ...


class PatientRepository(Protocol):
    async def get(self, patient_id: UUID) -> Patient: ...

    async def get_many(self, patient_ids: Collection[UUID]) -> dict[UUID, Patient]: ...

    async def for_contact(self, contact_id: UUID) -> list[Patient]: ...

    async def add(self, patient: Patient) -> None: ...

    async def save(self, patient: Patient) -> None: ...


class CaseRepository(Protocol):
    async def get(self, case_id: UUID) -> Case: ...

    async def open_case_of(self, patient_id: UUID) -> Case | None:
        """The patient's open case, if any (a new booking joins it - AP-10.1)."""
        ...

    async def for_patient(self, patient_id: UUID) -> list[Case]: ...

    async def add(self, case: Case) -> None: ...

    async def save(self, case: Case) -> None: ...


@dataclass(frozen=True)
class AppointmentFilter:
    start_from: datetime | None = None
    start_to: datetime | None = None
    doctor_id: UUID | None = None
    patient_id: UUID | None = None
    contact_id: UUID | None = None
    case_id: UUID | None = None
    statuses: Collection[AppointmentStatus] = ()
    pending_change_only: bool = False
    limit: int = 200


class AppointmentRepository(Protocol):
    async def get(self, appointment_id: UUID) -> Appointment: ...

    async def find_by_reference(self, reference: str) -> Appointment | None: ...

    async def search(self, query: AppointmentFilter) -> list[Appointment]: ...

    async def add(self, appointment: Appointment) -> None:
        """Retries `appointment.reference` on the rare clash."""
        ...

    async def save(self, appointment: Appointment) -> None: ...


class HoldKind(StrEnum):
    APPOINTMENT = "appointment"
    RESCHEDULE = "reschedule"


class SlotReservations(Protocol):
    """Who holds which doctor time. The ONLY guard against double-booking (AP-2.6):
    `reserve` serialises per doctor and refuses overlaps, even under concurrent requests."""

    async def busy(
        self,
        doctor_id: UUID,
        start: datetime,
        end: datetime,
        *,
        exclude_appointment: UUID | None = None,
    ) -> list[tuple[datetime, datetime]]:
        """Active reservations overlapping [start, end) - except `exclude_appointment`'s own
        (so moving an appointment by 15 minutes does not clash with itself)."""
        ...

    async def reserve(self, appointment_id: UUID, slot: Slot, kind: HoldKind) -> None:
        """Raises SlotUnavailableError if another appointment's active reservation overlaps."""
        ...

    async def release(self, appointment_id: UUID, slot: Slot) -> None: ...

    async def promote(self, appointment_id: UUID, slot: Slot) -> None:
        """A reschedule hold becomes the appointment's reservation."""
        ...


@dataclass(frozen=True)
class HistoryEntry:
    event_type: str
    occurred_at: datetime
    actor: str
    channel: str
    data: dict[str, Any]


class AppointmentHistory(Protocol):
    async def for_appointment(self, appointment_id: UUID) -> list[HistoryEntry]: ...


class DeletionRequestRepository(Protocol):
    async def get(self, request_id: UUID) -> DeletionRequest:
        """Raises DeletionRequestNotFoundError."""
        ...

    async def pending_for_contact(self, contact_id: UUID) -> DeletionRequest | None: ...

    async def list(self, status: DeletionStatus | None, limit: int) -> list[DeletionRequest]:
        """Newest first."""
        ...

    async def add(self, request: DeletionRequest) -> None: ...

    async def save(self, request: DeletionRequest) -> None: ...
