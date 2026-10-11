"""Appointment reminders with action buttons (PRD AP-5.1, AP-5.2, PL-7.2, PL-7.3).

AppointmentConfirmed / AppointmentRescheduled -> one job per reminder time (e.g. 24 h, 2 h).
The job checks the appointment is still booked AT THAT TIME before sending; a reminder for
a time that has since moved is simply skipped (no need to cancel jobs on reschedule).

Buttons carry "rem:<action>:<appointment id>". Tapping one starts the matching flow from
anywhere (Flow.choice_prefixes): Confirm / Pay now -> ReminderAction, Reschedule / Cancel ->
those flows with the appointment already chosen.

Outside the 24 h window the platform sends the clinic's template for the slot instead
(TemplateFallback); the template's quick-reply buttons carry the same payloads.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from app.modules.appointments.application.ports import ClinicDirectory
from app.modules.appointments.application.unit_of_work import AppointmentsUnitOfWork
from app.modules.appointments.domain.errors import AppointmentNotFoundError
from app.modules.appointments.domain.policy import BookingPolicy
from app.modules.appointments.domain.status import BOOKED
from app.modules.appointments.presentation.whatsapp.formatting import when
from app.modules.appointments.presentation.whatsapp.payments import SUBJECT, ChatSender, money
from app.shared.application.conversation import Translator
from app.shared.application.events import StoredEvent
from app.shared.application.jobs import JobContext, JobScheduler, ScheduleJob
from app.shared.application.messaging import TemplateFallback
from app.shared.application.payments import Payments
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import Choice, menu

log = logging.getLogger(__name__)
REMINDER_JOB = "appointments.send_reminder"
CONFIRM, RESCHEDULE, CANCEL, PAY = "rem:confirm:", "rem:reschedule:", "rem:cancel:", "rem:pay:"


class ScheduleReminders:
    def __init__(
        self,
        uow_for: Callable[[TenantId], AppointmentsUnitOfWork],
        clinic: ClinicDirectory,
        jobs: JobScheduler,
        clock: Clock,
    ) -> None:
        self._uow_for, self._clinic, self._jobs, self._clock = uow_for, clinic, jobs, clock

    async def __call__(self, event: StoredEvent) -> None:
        tenant_id = event.tenant_id
        if tenant_id is None:
            return
        policy = BookingPolicy.from_settings(await self._clinic.settings(tenant_id))
        async with self._uow_for(tenant_id) as uow:
            try:
                appointment = await uow.appointments.get(UUID(event.payload["appointment_id"]))
            except AppointmentNotFoundError:
                return
        start, now = appointment.slot.start, self._clock.now()
        for before in policy.reminders:
            run_at = start - before
            if run_at <= now:
                continue  # booked too late for this one
            await self._jobs.schedule(
                ScheduleJob(
                    REMINDER_JOB,
                    run_at,
                    # same appointment + same time + same offset = one reminder (PL-7.3)
                    f"{REMINDER_JOB}:{appointment.id}:{start.isoformat()}:{before}",
                    tenant_id=tenant_id,
                    payload={"appointment_id": str(appointment.id), "start": start.isoformat()},
                )
            )


class SendReminder:
    def __init__(
        self,
        uow_for: Callable[[TenantId], AppointmentsUnitOfWork],
        clinic: ClinicDirectory,
        payments: Payments,
        sender: ChatSender,
        texts: Translator,
    ) -> None:
        self._uow_for, self._clinic, self._payments = uow_for, clinic, payments
        self._sender, self._texts = sender, texts

    async def __call__(self, ctx: JobContext) -> None:
        tenant_id = ctx.tenant_id
        assert tenant_id is not None
        async with self._uow_for(tenant_id) as uow:
            try:
                a = await uow.appointments.get(UUID(ctx.payload["appointment_id"]))
            except AppointmentNotFoundError:
                return
            if a.status not in BOOKED or a.slot.start != datetime.fromisoformat(
                ctx.payload["start"]
            ):
                return  # cancelled or moved since - that time's reminder no longer applies
            patient = await uow.patients.get(a.patient_id)
            doctor = await uow.doctors.get(a.slot.doctor_id)
        due = [
            p
            for p in await self._payments.for_subjects(tenant_id, SUBJECT, [a.id])
            if p.status == "pending"
        ]
        t, ref = self._texts.t, a.reference
        at = when(a.slot.start, await self._clinic.timezone(tenant_id, a.location_id))
        params = [patient.full_name, doctor.name, at, ref]
        lines = [
            t(
                "appointments.remind.body",
                patient=patient.full_name,
                doctor=doctor.name,
                when=at,
                ref=ref,
            )
        ]
        choices = [
            Choice(f"{CONFIRM}{a.id}", t("appointments.remind.confirm")),
            Choice(f"{RESCHEDULE}{a.id}", t("appointments.menu.reschedule")),
            Choice(f"{CANCEL}{a.id}", t("appointments.menu.cancel")),
        ]
        if due:
            amount = money(due[0].amount_minor, due[0].currency)
            lines.append(t("appointments.pay.due", amount=amount, ref=ref))
            choices.append(Choice(f"{PAY}{a.id}", t("appointments.pay.button")))
            params.append(amount)
        message = menu("\n".join(lines), choices, button=t("appointments.options"))
        fallback = TemplateFallback(
            "appointments.reminder_pay" if due else "appointments.reminder",
            tuple(params),
            tuple(c.id for c in choices),
        )
        sent = await self._sender.notify(
            tenant_id, a.contact_id, message, fallback=fallback, reminder=True
        )
        if not sent:
            log.info("reminder.skipped", extra={"appointment": str(a.id)})
