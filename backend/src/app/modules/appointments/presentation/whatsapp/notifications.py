"""Tell the patient on WhatsApp when the CLINIC changes something (PRD AP-3.2, AP-3.3, AP-4.4).

Runs as an outbox event handler, after the change is committed. Patients are not told about
their own actions (they already got a reply in the chat).

Limitation until templates arrive (Phase 2, PRD PL-4.2): WhatsApp only allows free text within
24 h of the patient's last message, so a notification outside that window is skipped and
logged. Delivery is at-least-once: in the rare case the handler runs twice, the patient may
get the same message twice.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from app.modules.appointments.application.ports import ClinicDirectory
from app.modules.appointments.application.unit_of_work import AppointmentsUnitOfWork
from app.modules.appointments.domain.errors import AppointmentNotFoundError
from app.modules.appointments.presentation.whatsapp.formatting import when
from app.shared.application.conversation import Translator
from app.shared.application.events import StoredEvent
from app.shared.kernel.ids import TenantId

log = logging.getLogger(__name__)

#: event type -> (text key, only when the clinic/system did it?)
NOTIFY: dict[str, tuple[str, bool]] = {
    "AppointmentConfirmed": ("appointments.notify.confirmed", True),
    "AppointmentDeclined": ("appointments.notify.declined", True),
    "AppointmentExpired": ("appointments.notify.expired", True),
    "AppointmentRescheduled": ("appointments.notify.rescheduled", True),
    "RescheduleDeclined": ("appointments.notify.reschedule_declined", True),
    "AppointmentCancelled": ("appointments.notify.cancelled", True),
}


class PatientNotifier(Protocol):
    async def notify(self, tenant_id: TenantId, contact_id: UUID, text: str) -> bool:
        """False if it could not be sent (e.g. outside the 24 h window, no number)."""
        ...


class NotifyPatient:
    def __init__(
        self,
        uow_for: Callable[[TenantId], AppointmentsUnitOfWork],
        clinic: ClinicDirectory,
        notifier: PatientNotifier,
        texts: Translator,
    ) -> None:
        self._uow_for, self._clinic, self._notifier, self._texts = uow_for, clinic, notifier, texts

    async def __call__(self, event: StoredEvent) -> None:
        rule = NOTIFY.get(event.event_type)
        if rule is None or event.tenant_id is None:
            return
        key, clinic_only = rule
        if clinic_only and event.payload["actor"]["kind"] == "contact":
            return  # the patient did it themselves and was answered in the chat
        if event.event_type == "AppointmentConfirmed" and event.payload.get("automatic"):
            return  # auto-confirmed bookings were confirmed in the chat already

        async with self._uow_for(event.tenant_id) as uow:
            try:
                appointment = await uow.appointments.get(UUID(event.payload["appointment_id"]))
            except AppointmentNotFoundError:
                return  # deleted since (on request / retention) - nothing left to talk about
            doctor = await uow.doctors.get(appointment.doctor_id)
        timezone = await self._clinic.timezone(event.tenant_id, appointment.location_id)
        text = self._texts.t(
            key,
            ref=appointment.reference,
            when=when(appointment.slot.start, timezone),
            doctor=doctor.name,
            reason=(event.payload.get("reason") or "").strip(),
        ).strip()
        if not await self._notifier.notify(event.tenant_id, appointment.contact_id, text):
            log.info(
                "notification.skipped",
                extra={"event": event.event_type, "appointment": str(appointment.id)},
            )


#: Deletion requests (AP-10.10, AP-10.11): event type -> text key.
DELETION_NOTICES: dict[str, str] = {
    "DeletionRequestCompleted": "appointments.delete.completed",
    "DeletionRequestRejected": "appointments.delete.rejected",
}


class NotifyDeletionDecision:
    def __init__(self, notifier: PatientNotifier, texts: Translator) -> None:
        self._notifier, self._texts = notifier, texts

    async def __call__(self, event: StoredEvent) -> None:
        key = DELETION_NOTICES.get(event.event_type)
        if key is None or event.tenant_id is None:
            return
        text = self._texts.t(key, reason=event.payload.get("reason", "")).strip()
        contact_id = UUID(event.payload["contact_id"])
        if not await self._notifier.notify(event.tenant_id, contact_id, text):
            log.info("notification.skipped", extra={"event": event.event_type})
