from __future__ import annotations

from app.shared.kernel.errors import DomainError, NotFoundError


class DoctorNotFoundError(NotFoundError):
    code = "appointments.doctor_not_found"


class PatientNotFoundError(NotFoundError):
    code = "appointments.patient_not_found"


class AppointmentNotFoundError(NotFoundError):
    code = "appointments.not_found"


class CaseNotFoundError(NotFoundError):
    code = "appointments.case_not_found"


class InvalidDoctorError(DomainError):
    code = "appointments.invalid_doctor"


class InvalidScheduleError(DomainError):
    """Working hours / time off that make no sense (overlaps, end before start ...)."""

    code = "appointments.invalid_schedule"


class SlotUnavailableError(DomainError):
    """Not a bookable slot: outside working hours, in the past, taken, time off ..."""

    code = "appointments.slot_unavailable"


class InvalidTransitionError(DomainError):
    code = "appointments.invalid_transition"


class SameSlotError(DomainError):
    code = "appointments.same_slot"


class ChangeCutoffPassedError(DomainError):
    """Too close to the appointment for the patient to change it (PRD AP-4.8)."""

    code = "appointments.cutoff_passed"


class NoPendingChangeError(DomainError):
    code = "appointments.no_pending_change"


class InvalidBookingFieldsError(DomainError):
    code = "appointments.invalid_fields"


class ReasonRequiredError(DomainError):
    code = "appointments.reason_required"


class CaseHasActiveAppointmentsError(DomainError):
    """A case can only close when nothing is upcoming (PRD AP-10.3)."""

    code = "appointments.case_has_active_appointments"


class CaseClosedError(DomainError):
    code = "appointments.case_closed"


class InvalidPatientError(DomainError):
    code = "appointments.invalid_patient"
