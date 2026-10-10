"""Everything the appointments module plugs into the platform (ARCHITECTURE §8.1)."""

from __future__ import annotations

from app.modules.appointments.application.commands.decisions import (
    EXPIRE_REQUEST_JOB,
    EXPIRE_RESCHEDULE_JOB,
)
from app.modules.appointments.presentation.http.routers import HTTP_ERROR_STATUS
from app.modules.appointments.presentation.whatsapp.notifications import (
    DELETION_NOTICES,
    NOTIFY,
)
from app.modules.appointments.wiring import (
    LOCALES,
    MODULE_KEY,
    book_flow,
    build_routers,
    cancel_flow,
    case_purger,
    delete_data_flow,
    expire_stale,
    menu_flow,
    new_contact_rule,
    notify_deletion_decision,
    notify_patient,
    reschedule_flow,
    returning_contact_rule,
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
        "case.manage": "Close and reopen cases, set legal holds, decide data deletion requests",
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
        **{event_type: [notify_patient] for event_type in NOTIFY},
        **{event_type: [notify_deletion_decision] for event_type in DELETION_NOTICES},
    },
    # WhatsApp (PRD §7.1): rules pick the flow for a new conversation; flows are the chats.
    router_rules=[returning_contact_rule, new_contact_rule],
    flows=[book_flow, menu_flow, reschedule_flow, cancel_flow, delete_data_flow],
    locales_dir=LOCALES,
    purgers=[case_purger],  # RT-1..RT-3
)
