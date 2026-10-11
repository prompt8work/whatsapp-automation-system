"""Appointment events. Each one is ALSO a row of the appointment's history (PRD §7.8):
the Unit of Work writes events that carry an `appointment_id` to `appointment_events`
(append-only) in the same transaction as the change.

Ids, times and statuses only - no names, phone numbers or reasons for visit (those stay in the
appointment row, which the retention purge deletes; history rows go with it).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.shared.kernel.actor import Actor, Channel
from app.shared.kernel.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class AppointmentEvent(DomainEvent):
    appointment_id: UUID
    actor: Actor
    channel: Channel


@dataclass(frozen=True, kw_only=True)
class AppointmentRequested(AppointmentEvent):
    case_id: UUID
    patient_id: UUID
    doctor_id: UUID
    start: datetime
    end: datetime
    needs_approval: bool


@dataclass(frozen=True, kw_only=True)
class AppointmentConfirmed(AppointmentEvent):
    automatic: bool  # True when the clinic does not require approval


@dataclass(frozen=True, kw_only=True)
class AppointmentDeclined(AppointmentEvent):
    reason: str


@dataclass(frozen=True, kw_only=True)
class AppointmentExpired(AppointmentEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class AppointmentCancelled(AppointmentEvent):
    reason: str


@dataclass(frozen=True, kw_only=True)
class RescheduleRequested(AppointmentEvent):
    current_start: datetime
    requested_start: datetime
    requested_end: datetime
    doctor_id: UUID


@dataclass(frozen=True, kw_only=True)
class AppointmentRescheduled(AppointmentEvent):
    old_start: datetime
    old_end: datetime
    new_start: datetime
    new_end: datetime
    old_doctor_id: UUID
    new_doctor_id: UUID


@dataclass(frozen=True, kw_only=True)
class RescheduleDeclined(AppointmentEvent):
    requested_start: datetime
    reason: str


@dataclass(frozen=True, kw_only=True)
class AppointmentCompleted(AppointmentEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class AppointmentNoShow(AppointmentEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class AttendanceConfirmed(AppointmentEvent):
    """The patient tapped "Confirm" on a reminder (AP-5.1). History only - no status change."""


@dataclass(frozen=True, kw_only=True)
class AppointmentDetailsUpdated(AppointmentEvent):
    changed: tuple[str, ...]  # field names only (values may be personal data)


# ------------------------------------------------------------------ other aggregates
@dataclass(frozen=True, kw_only=True)
class PatientRegistered(DomainEvent):
    patient_id: UUID
    contact_id: UUID
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class PatientUpdated(DomainEvent):
    patient_id: UUID
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class CaseOpened(DomainEvent):
    case_id: UUID
    patient_id: UUID


@dataclass(frozen=True, kw_only=True)
class CaseClosed(DomainEvent):
    case_id: UUID
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class CaseReopened(DomainEvent):
    case_id: UUID
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class DoctorChanged(DomainEvent):
    doctor_id: UUID
    what: str  # "added" | "updated" | "working_hours" | "time_off"
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class CasePurged(DomainEvent):
    """Retention deleted the case (RT-1/RT-2/AP-10.11). Payments detach their records (RT-7)."""

    case_id: UUID
    patient_id: UUID
    patient_deleted: bool
    rule: str
    appointment_ids: tuple[UUID, ...] = ()  # gone too; payments keep their ledger (RT-7)


@dataclass(frozen=True, kw_only=True)
class DeletionRequested(DomainEvent):
    request_id: UUID
    contact_id: UUID


@dataclass(frozen=True, kw_only=True)
class DeletionRequestRejected(DomainEvent):
    request_id: UUID
    contact_id: UUID
    reason: str  # written by staff for the patient; no health details expected
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class DeletionRequestCompleted(DomainEvent):
    request_id: UUID
    contact_id: UUID
    actor: Actor
