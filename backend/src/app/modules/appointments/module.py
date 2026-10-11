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
from app.modules.appointments.presentation.whatsapp.payments import ENDED_UNPAID, RECEIPTS
from app.modules.appointments.presentation.whatsapp.reminders import REMINDER_JOB
from app.modules.appointments.presentation.whatsapp.templates import TEMPLATE_SLOTS
from app.modules.appointments.wiring import (
    LOCALES,
    MODULE_KEY,
    book_flow,
    build_routers,
    cancel_flow,
    case_purger,
    delete_data_flow,
    detach_payments,
    expire_payment,
    expire_stale,
    menu_flow,
    new_contact_rule,
    notify_deletion_decision,
    notify_patient,
    payment_receipt,
    reminder_flow,
    request_payment,
    reschedule_flow,
    returning_contact_rule,
    schedule_expiry,
    schedule_reminders,
    send_reminder,
)
from app.shared.kernel.roles import Role
from app.shared.module import EventHandlerFactory, ModuleDefinition

STAFF_PERMISSIONS = {
    "appointment.read",
    "appointment.read_all",
    "appointment.create",
    "appointment.approve",
    "appointment.manage",
    "appointment.attendance",
    "case.manage",
}


def _event_handlers() -> dict[str, list[EventHandlerFactory]]:
    handlers: dict[str, list[EventHandlerFactory]] = {
        "AppointmentRequested": [schedule_expiry],
        "RescheduleRequested": [schedule_expiry],
        "CasePurged": [detach_payments],  # RT-7
    }

    def add(event_type: str, factory: EventHandlerFactory) -> None:
        handlers.setdefault(event_type, []).append(factory)

    for event_type in NOTIFY:
        add(event_type, notify_patient)
    for event_type in DELETION_NOTICES:
        add(event_type, notify_deletion_decision)
    add("AppointmentConfirmed", request_payment)  # after the "Confirmed" message
    add("AppointmentConfirmed", schedule_reminders)
    add("AppointmentRescheduled", schedule_reminders)
    for event_type in ENDED_UNPAID:
        add(event_type, expire_payment)
    for event_type in RECEIPTS:
        add(event_type, payment_receipt)
    return handlers


def _live_topics() -> dict[str, tuple[str, ...]]:
    """Dashboard areas each event changes (live updates, ARCHITECTURE §8.9)."""
    from app.modules.appointments.domain import events
    from app.shared.kernel.events import DomainEvent

    topics: dict[str, tuple[str, ...]] = {
        name: ("appointments",)
        for name, cls in vars(events).items()
        if isinstance(cls, type) and issubclass(cls, DomainEvent) and cls is not DomainEvent
    }
    for name in ("DeletionRequested", "DeletionRequestRejected", "DeletionRequestCompleted"):
        topics[name] = ("privacy",)
    topics["CasePurged"] = ("appointments", "privacy")
    return topics


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
    job_handlers={
        EXPIRE_REQUEST_JOB: expire_stale,
        EXPIRE_RESCHEDULE_JOB: expire_stale,
        REMINDER_JOB: send_reminder,
    },
    event_handlers=_event_handlers(),
    # WhatsApp (PRD §7.1): rules pick the flow for a new conversation; flows are the chats.
    router_rules=[returning_contact_rule, new_contact_rule],
    flows=[book_flow, menu_flow, reschedule_flow, cancel_flow, delete_data_flow, reminder_flow],
    template_slots=TEMPLATE_SLOTS,
    live_topics=_live_topics(),
    locales_dir=LOCALES,
    purgers=[case_purger],  # RT-1..RT-3
)
