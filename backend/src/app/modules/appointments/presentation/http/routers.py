"""Appointments dashboard API (mounted under /api). Thin: request -> command -> use case ->
response.

Static paths (/appointments/requests, /appointments/settings) are declared before
/appointments/{id} so they are matched first.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, time
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import AwareDatetime

from app.modules.appointments.application.commands.booking import RequestAppointmentCommand
from app.modules.appointments.application.commands.changes import (
    AttendanceCommand,
    CancelCommand,
    RescheduleCommand,
    UpdateDetailsCommand,
)
from app.modules.appointments.application.commands.decisions import DecisionCommand
from app.modules.appointments.application.commands.doctors import (
    AddDoctorCommand,
    SetWorkingHoursCommand,
    TimeOffCommand,
    UpdateDoctorCommand,
)
from app.modules.appointments.application.commands.patients import (
    CaseCommand,
    LegalHoldCommand,
    RegisterPatientForPhoneCommand,
    RenamePatientCommand,
)
from app.modules.appointments.application.queries.reads import (
    DetailQuery,
    ListAppointmentsQuery,
    SlotsQuery,
)
from app.modules.appointments.application.use_cases import AppointmentsUseCases
from app.modules.appointments.domain.status import AppointmentStatus
from app.modules.appointments.domain.values import WorkingHours
from app.modules.appointments.presentation.http.schemas import (
    AddDoctorRequest,
    AddTimeOffRequest,
    AppointmentDetailResponse,
    AppointmentResponse,
    AppointmentSettings,
    AttendanceRequest,
    BookRequest,
    CaseResponse,
    CloseCaseRequest,
    DoctorResponse,
    LegalHoldRequest,
    PatientResponse,
    ReasonRequest,
    RegisterPatientRequest,
    RenamePatientRequest,
    RescheduleRequest,
    SlotSchema,
    SlotsResponse,
    UpdateDetailsRequest,
    UpdateDoctorRequest,
    WorkingHoursSchema,
)
from app.shared.kernel.actor import Actor, Channel
from app.shared.kernel.ids import TenantId
from app.shared.presentation.request_context import RequestContext, require

HTTP_ERROR_STATUS = {
    "appointments.doctor_not_found": status.HTTP_404_NOT_FOUND,
    "appointments.patient_not_found": status.HTTP_404_NOT_FOUND,
    "appointments.not_found": status.HTTP_404_NOT_FOUND,
    "appointments.case_not_found": status.HTTP_404_NOT_FOUND,
    "appointments.invalid_doctor": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "appointments.invalid_schedule": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "appointments.invalid_fields": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "appointments.reason_required": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "appointments.invalid_patient": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "appointments.slot_unavailable": status.HTTP_409_CONFLICT,
    "appointments.invalid_transition": status.HTTP_409_CONFLICT,
    "appointments.same_slot": status.HTTP_409_CONFLICT,
    "appointments.cutoff_passed": status.HTTP_409_CONFLICT,
    "appointments.no_pending_change": status.HTTP_409_CONFLICT,
    "appointments.case_has_active_appointments": status.HTTP_409_CONFLICT,
    "appointments.case_closed": status.HTTP_409_CONFLICT,
}


CanRead = Annotated[RequestContext, Depends(require("appointment.read"))]
CanCreate = Annotated[RequestContext, Depends(require("appointment.create"))]
CanApprove = Annotated[RequestContext, Depends(require("appointment.approve"))]
CanManage = Annotated[RequestContext, Depends(require("appointment.manage"))]
CanMarkAttendance = Annotated[RequestContext, Depends(require("appointment.attendance"))]
CanManageDoctors = Annotated[RequestContext, Depends(require("doctor.manage"))]
CanManageCases = Annotated[RequestContext, Depends(require("case.manage"))]
CanManageSettings = Annotated[RequestContext, Depends(require("appointment.settings.manage"))]
AwareDatetimeQuery = Annotated[AwareDatetime | None, Query()]


def _own_only(ctx: RequestContext) -> UUID | None:
    """Doctors without `appointment.read_all` only see their own appointments (AP-7.2)."""
    return None if ctx.principal.can("appointment.read_all") else ctx.principal.user_id


class SettingsStore:
    """Reads/writes the tenant's appointments settings through the tenancy facade."""

    def __init__(
        self,
        read: Callable[[TenantId], Awaitable[dict[str, Any]]],
        write: Callable[[TenantId, dict[str, Any], Actor], Awaitable[None]],
    ) -> None:
        self.read, self.write = read, write


def build_router(
    for_tenant: Callable[[TenantId], AppointmentsUseCases], settings: SettingsStore
) -> APIRouter:
    router = APIRouter(tags=["appointments"])
    dash = Channel.DASHBOARD

    # ------------------------------------------------------------------ doctors
    @router.get("/doctors")
    async def list_doctors(ctx: CanRead, active_only: bool = False) -> list[DoctorResponse]:
        doctors = await for_tenant(ctx.tenant_id).list_doctors(active_only=active_only)
        return [DoctorResponse.from_dto(d) for d in doctors]

    @router.post("/doctors", status_code=status.HTTP_201_CREATED)
    async def add_doctor(body: AddDoctorRequest, ctx: CanManageDoctors) -> DoctorResponse:
        doctor = await for_tenant(ctx.tenant_id).add_doctor(
            AddDoctorCommand(
                ctx.tenant_id,
                body.location_id,
                body.name,
                body.specialty,
                body.slot_minutes,
                ctx.actor,
                body.user_id,
            )
        )
        return DoctorResponse.from_dto(doctor)

    @router.patch("/doctors/{doctor_id}")
    async def update_doctor(
        doctor_id: UUID, body: UpdateDoctorRequest, ctx: CanManageDoctors
    ) -> DoctorResponse:
        doctor = await for_tenant(ctx.tenant_id).update_doctor(
            UpdateDoctorCommand(
                ctx.tenant_id, doctor_id, ctx.actor, **body.model_dump(exclude_unset=True)
            )
        )
        return DoctorResponse.from_dto(doctor)

    @router.put("/doctors/{doctor_id}/working-hours")
    async def set_working_hours(
        doctor_id: UUID, body: list[WorkingHoursSchema], ctx: CanManageDoctors
    ) -> DoctorResponse:
        hours = [WorkingHours(h.weekday, h.start, h.end) for h in body]
        doctor = await for_tenant(ctx.tenant_id).set_working_hours(
            SetWorkingHoursCommand(doctor_id, hours, ctx.actor)
        )
        return DoctorResponse.from_dto(doctor)

    @router.post("/doctors/{doctor_id}/time-off", status_code=status.HTTP_201_CREATED)
    async def add_time_off(
        doctor_id: UUID, body: AddTimeOffRequest, ctx: CanManageDoctors
    ) -> DoctorResponse:
        doctor = await for_tenant(ctx.tenant_id).change_time_off(
            TimeOffCommand(doctor_id, ctx.actor, start=body.start, end=body.end, reason=body.reason)
        )
        return DoctorResponse.from_dto(doctor)

    @router.delete("/doctors/{doctor_id}/time-off/{time_off_id}")
    async def remove_time_off(
        doctor_id: UUID, time_off_id: UUID, ctx: CanManageDoctors
    ) -> DoctorResponse:
        doctor = await for_tenant(ctx.tenant_id).change_time_off(
            TimeOffCommand(doctor_id, ctx.actor, remove_id=time_off_id)
        )
        return DoctorResponse.from_dto(doctor)

    @router.get("/doctors/{doctor_id}/slots")
    async def free_slots(
        doctor_id: UUID, ctx: CanRead, day: Annotated[date, Query(alias="date")]
    ) -> SlotsResponse:
        result = await for_tenant(ctx.tenant_id).find_free_slots(
            SlotsQuery(ctx.tenant_id, doctor_id, day)
        )
        return SlotsResponse(
            date=day, timezone=result.timezone, slots=[SlotSchema.from_dto(s) for s in result.slots]
        )

    # ------------------------------------------------------------------ patients & cases
    @router.post("/patients", status_code=status.HTTP_201_CREATED)
    async def register_patient(body: RegisterPatientRequest, ctx: CanCreate) -> PatientResponse:
        patient = await for_tenant(ctx.tenant_id).register_patient_for_phone(
            RegisterPatientForPhoneCommand(ctx.tenant_id, body.phone, body.full_name, ctx.actor)
        )
        return PatientResponse.from_dto(patient)

    @router.patch("/patients/{patient_id}")
    async def rename_patient(
        patient_id: UUID, body: RenamePatientRequest, ctx: CanManage
    ) -> PatientResponse:
        patient = await for_tenant(ctx.tenant_id).rename_patient(
            RenamePatientCommand(patient_id, body.full_name, ctx.actor)
        )
        return PatientResponse.from_dto(patient)

    @router.get("/patients/{patient_id}/cases")
    async def patient_cases(patient_id: UUID, ctx: CanRead) -> list[CaseResponse]:
        return [
            CaseResponse.from_dto(c)
            for c in await for_tenant(ctx.tenant_id).cases_of_patient(patient_id)
        ]

    @router.post("/cases/{case_id}/close")
    async def close_case(
        case_id: UUID, body: CloseCaseRequest, ctx: CanManageCases
    ) -> CaseResponse:
        case = await for_tenant(ctx.tenant_id).close_case(
            CaseCommand(case_id, ctx.actor, body.note)
        )
        return CaseResponse.from_dto(case)

    @router.post("/cases/{case_id}/reopen")
    async def reopen_case(case_id: UUID, ctx: CanManageCases) -> CaseResponse:
        return CaseResponse.from_dto(
            await for_tenant(ctx.tenant_id).reopen_case(CaseCommand(case_id, ctx.actor))
        )

    @router.put("/cases/{case_id}/legal-hold")
    async def legal_hold(
        case_id: UUID, body: LegalHoldRequest, ctx: CanManageCases
    ) -> CaseResponse:
        case = await for_tenant(ctx.tenant_id).set_legal_hold(
            LegalHoldCommand(case_id, body.hold, ctx.actor)
        )
        return CaseResponse.from_dto(case)

    # ------------------------------------------------- appointments (static paths before /{id})
    @router.get("/appointments/requests")
    async def request_queue(ctx: CanApprove) -> list[AppointmentResponse]:
        return [
            AppointmentResponse.from_dto(a) for a in await for_tenant(ctx.tenant_id).list_requests()
        ]

    @router.get("/appointments/settings")
    async def get_settings(ctx: CanRead) -> AppointmentSettings:
        return AppointmentSettings.model_validate(await settings.read(ctx.tenant_id))

    @router.put("/appointments/settings")
    async def put_settings(
        body: AppointmentSettings, ctx: CanManageSettings
    ) -> AppointmentSettings:
        await settings.write(ctx.tenant_id, body.model_dump(mode="json"), ctx.actor)
        return body

    @router.get("/appointments")
    async def list_appointments(
        ctx: CanRead,
        start_from: AwareDatetimeQuery = None,
        start_to: AwareDatetimeQuery = None,
        on: Annotated[date | None, Query(description="All appointments on this UTC day")] = None,
        doctor_id: UUID | None = None,
        patient_id: UUID | None = None,
        status_in: Annotated[list[AppointmentStatus] | None, Query(alias="status")] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
    ) -> list[AppointmentResponse]:
        if on is not None:
            start_from = datetime.combine(on, time(), UTC)
            start_to = datetime.combine(on, time.max, UTC)
        found = await for_tenant(ctx.tenant_id).list_appointments(
            ListAppointmentsQuery(
                start_from=start_from,
                start_to=start_to,
                doctor_id=doctor_id,
                patient_id=patient_id,
                statuses=status_in or (),
                only_for_user=_own_only(ctx),
                limit=limit,
            )
        )
        return [AppointmentResponse.from_dto(a) for a in found]

    @router.post("/appointments", status_code=status.HTTP_201_CREATED)
    async def book(body: BookRequest, ctx: CanCreate) -> AppointmentResponse:
        appointment = await for_tenant(ctx.tenant_id).request(
            RequestAppointmentCommand(
                ctx.tenant_id,
                body.patient_id,
                body.doctor_id,
                body.start,
                ctx.actor,
                dash,
                body.reason,
                body.fields,
            )
        )
        return AppointmentResponse.from_dto(appointment)

    @router.get("/appointments/{appointment_id}")
    async def detail(appointment_id: UUID, ctx: CanRead) -> AppointmentDetailResponse:
        found = await for_tenant(ctx.tenant_id).detail(
            DetailQuery(ctx.tenant_id, appointment_id, ctx.actor, only_for_user=_own_only(ctx))
        )
        return AppointmentDetailResponse.from_dto(found)

    @router.patch("/appointments/{appointment_id}")
    async def update_details(
        appointment_id: UUID, body: UpdateDetailsRequest, ctx: CanManage
    ) -> AppointmentResponse:
        appointment = await for_tenant(ctx.tenant_id).update_details(
            UpdateDetailsCommand(
                ctx.tenant_id, appointment_id, ctx.actor, dash, body.reason, body.fields
            )
        )
        return AppointmentResponse.from_dto(appointment)

    @router.post("/appointments/{appointment_id}/approve")
    async def approve(appointment_id: UUID, ctx: CanApprove) -> AppointmentResponse:
        return AppointmentResponse.from_dto(
            await for_tenant(ctx.tenant_id).approve(DecisionCommand(appointment_id, ctx.actor))
        )

    @router.post("/appointments/{appointment_id}/decline")
    async def decline(
        appointment_id: UUID, body: ReasonRequest, ctx: CanApprove
    ) -> AppointmentResponse:
        return AppointmentResponse.from_dto(
            await for_tenant(ctx.tenant_id).decline(
                DecisionCommand(appointment_id, ctx.actor, reason=body.reason)
            )
        )

    @router.post("/appointments/{appointment_id}/reschedule")
    async def reschedule(
        appointment_id: UUID, body: RescheduleRequest, ctx: CanManage
    ) -> AppointmentResponse:
        appointment = await for_tenant(ctx.tenant_id).reschedule(
            RescheduleCommand(
                ctx.tenant_id, appointment_id, body.start, ctx.actor, dash, body.doctor_id
            )
        )
        return AppointmentResponse.from_dto(appointment)

    @router.post("/appointments/{appointment_id}/reschedule/approve")
    async def approve_reschedule(appointment_id: UUID, ctx: CanApprove) -> AppointmentResponse:
        return AppointmentResponse.from_dto(
            await for_tenant(ctx.tenant_id).approve_reschedule(
                DecisionCommand(appointment_id, ctx.actor)
            )
        )

    @router.post("/appointments/{appointment_id}/reschedule/decline")
    async def decline_reschedule(
        appointment_id: UUID, body: ReasonRequest, ctx: CanApprove
    ) -> AppointmentResponse:
        return AppointmentResponse.from_dto(
            await for_tenant(ctx.tenant_id).decline_reschedule(
                DecisionCommand(appointment_id, ctx.actor, reason=body.reason)
            )
        )

    @router.post("/appointments/{appointment_id}/cancel")
    async def cancel(
        appointment_id: UUID, body: ReasonRequest, ctx: CanManage
    ) -> AppointmentResponse:
        appointment = await for_tenant(ctx.tenant_id).cancel(
            CancelCommand(ctx.tenant_id, appointment_id, ctx.actor, dash, body.reason)
        )
        return AppointmentResponse.from_dto(appointment)

    @router.post("/appointments/{appointment_id}/attendance")
    async def attendance(
        appointment_id: UUID, body: AttendanceRequest, ctx: CanMarkAttendance
    ) -> AppointmentResponse:
        appointment = await for_tenant(ctx.tenant_id).record_attendance(
            AttendanceCommand(appointment_id, body.attended, ctx.actor)
        )
        return AppointmentResponse.from_dto(appointment)

    return router
