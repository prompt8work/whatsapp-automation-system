"""All appointment use cases for ONE tenant (built per request by wiring.py)."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.appointments.application.commands.booking import RequestAppointment
from app.modules.appointments.application.commands.changes import (
    CancelAppointment,
    ConfirmAttendance,
    RecordAttendance,
    RescheduleAppointment,
    UpdateAppointmentDetails,
)
from app.modules.appointments.application.commands.decisions import (
    ApproveRequest,
    ApproveReschedule,
    DeclineRequest,
    DeclineReschedule,
)
from app.modules.appointments.application.commands.deletion import (
    ApproveDeletion,
    ListDeletionRequests,
    PendingDeletionOf,
    RejectDeletion,
    RequestDeletion,
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


@dataclass(frozen=True)
class AppointmentsUseCases:
    # doctors
    add_doctor: AddDoctor
    update_doctor: UpdateDoctor
    set_working_hours: SetWorkingHours
    change_time_off: ChangeTimeOff
    list_doctors: ListDoctors
    find_free_slots: FindFreeSlots
    # patients & cases
    register_patient: RegisterPatient
    register_patient_for_phone: RegisterPatientForPhone
    rename_patient: RenamePatient
    patients_of_contact: PatientsOfContact
    cases_of_patient: CasesOfPatient
    close_case: CloseCase
    reopen_case: ReopenCase
    set_legal_hold: SetLegalHold
    # appointments
    request: RequestAppointment
    approve: ApproveRequest
    decline: DeclineRequest
    reschedule: RescheduleAppointment
    approve_reschedule: ApproveReschedule
    decline_reschedule: DeclineReschedule
    cancel: CancelAppointment
    record_attendance: RecordAttendance
    confirm_attendance: ConfirmAttendance
    update_details: UpdateAppointmentDetails
    list_appointments: ListAppointments
    list_requests: ListRequests
    detail: GetAppointmentDetail
    upcoming_for_contact: UpcomingForContact
    # deletion on request (PRD AP-10.8-10.13)
    request_deletion: RequestDeletion
    pending_deletion_of: PendingDeletionOf
    list_deletion_requests: ListDeletionRequests
    approve_deletion: ApproveDeletion
    reject_deletion: RejectDeletion
