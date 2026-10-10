"""Everything the appointments module plugs into the platform (ARCHITECTURE §8.1)."""

from __future__ import annotations

from pathlib import Path

from app.modules.appointments.application.commands.decisions import (
    EXPIRE_REQUEST_JOB,
    EXPIRE_RESCHEDULE_JOB,
)
from app.modules.appointments.presentation.http.routers import HTTP_ERROR_STATUS
from app.modules.appointments.wiring import (
    MODULE_KEY,
    build_routers,
    expire_stale,
    schedule_expiry,
)
from app.shared.kernel.roles import Role
from app.shared.module import ModuleDefinition

STAFF_PERMISSIONS = {
    "appointment.read",
    "appointment.read_all",
    "appointment.create",
    "appointment.approve",
    "appointment.manage",
    "appointment.attendance",
    "case.manage",
}

module = ModuleDefinition(
    key=MODULE_KEY,
    build_routers=build_routers,
    http_error_status=HTTP_ERROR_STATUS,
    permissions={
        "appointment.read": "See appointments (doctors: their own)",
        "appointment.read_all": "See every doctor's appointments",
        "appointment.create": "Register patients and book appointments",
        "appointment.approve": "Approve or decline requests and reschedules",
        "appointment.manage": "Reschedule, cancel and edit appointments",
        "appointment.attendance": "Mark appointments completed or no-show",
        "case.manage": "Close and reopen cases, set legal holds",
        "doctor.manage": "Add doctors and change their hours",
        "appointment.settings.manage": "Change booking rules",
    },
    role_grants={
        Role.STAFF: STAFF_PERMISSIONS,
        Role.DOCTOR: {"appointment.read", "appointment.attendance"},
    },
    job_handlers={EXPIRE_REQUEST_JOB: expire_stale, EXPIRE_RESCHEDULE_JOB: expire_stale},
    event_handlers={
        "AppointmentRequested": [schedule_expiry],
        "RescheduleRequested": [schedule_expiry],
    },
    locales_dir=Path(__file__).parent / "locales",
)
