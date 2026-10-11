"""Payments in the patient's chat (PRD §7.5, PL-6.1 - PL-6.6), as outbox event handlers.

AppointmentConfirmed            -> ask for the consultation fee (Pay now / payable at clinic)
Cancelled/Declined/Expired/NoShow -> the pending payment is no longer due (PL-6.5)
PaymentSucceeded / Refunded     -> receipt on WhatsApp (AP-5.3)
CasePurged                      -> detach the payments: they stay as ledger entries (RT-7)

Payments only change through payments' own use cases; this module just asks and listens.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from app.modules.appointments.application.ports import ClinicDirectory, PatientContacts
from app.modules.appointments.application.unit_of_work import AppointmentsUnitOfWork
from app.modules.appointments.domain.errors import AppointmentNotFoundError
from app.modules.appointments.domain.policy import BookingPolicy
from app.modules.appointments.presentation.whatsapp.notifications import PatientNotifier
from app.modules.appointments.presentation.whatsapp.templates import update_fallback
from app.shared.application.conversation import Translator
from app.shared.application.events import StoredEvent
from app.shared.application.messaging import TemplateFallback
from app.shared.application.payments import PaymentAsk, Payments
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import OutboundMessage

log = logging.getLogger(__name__)
SUBJECT = "appointment"
ENDED_UNPAID = (
    "AppointmentCancelled",
    "AppointmentDeclined",
    "AppointmentExpired",
    "AppointmentNoShow",
)
RECEIPTS = {
    "PaymentSucceeded": "appointments.pay.receipt",
    "PaymentRefunded": "appointments.pay.refunded",
}


def money(amount_minor: int, currency: str = "INR") -> str:
    """₹500, ₹12,34,567.89 - Indian digit grouping (lakh, crore)."""
    symbol = {"INR": "₹"}.get(currency, currency + " ")
    whole, paise = divmod(amount_minor, 100)
    digits = str(whole)
    head, tail = digits[:-3], digits[-3:]
    groups: list[str] = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    grouped = ",".join([*groups, tail])
    return f"{symbol}{grouped}" + (f".{paise:02d}" if paise else "")


ChatSender = PatientNotifier


async def pay_prompt(
    payments: Payments,
    texts: Translator,
    tenant_id: TenantId,
    payment_id: UUID,
    amount_minor: int,
    reference: str,
) -> OutboundMessage | str:
    """The Pay now message, or - for Pay at clinic - a line saying what is due there (PL-6.6)."""
    amount = money(amount_minor)
    message = await payments.pay_message(
        tenant_id,
        payment_id,
        texts.t("appointments.pay.ask", amount=amount, ref=reference),
        texts.t("appointments.pay.button"),
    )
    return message or texts.t("appointments.pay.at_clinic", amount=amount, ref=reference)


class RequestAppointmentPayment:
    def __init__(
        self,
        uow_for: Callable[[TenantId], AppointmentsUnitOfWork],
        clinic: ClinicDirectory,
        contacts: PatientContacts,
        payments: Payments,
        sender: ChatSender,
        texts: Translator,
    ) -> None:
        self._uow_for, self._clinic, self._contacts = uow_for, clinic, contacts
        self._payments, self._sender, self._texts = payments, sender, texts

    async def __call__(self, event: StoredEvent) -> None:
        tenant_id = event.tenant_id
        if tenant_id is None:
            return
        policy = BookingPolicy.from_settings(await self._clinic.settings(tenant_id))
        if policy.fee_minor <= 0 or await self._payments.primary_method(tenant_id) is None:
            return  # this clinic does not take payments here
        async with self._uow_for(tenant_id) as uow:
            try:
                appointment = await uow.appointments.get(UUID(event.payload["appointment_id"]))
            except AppointmentNotFoundError:
                return
            patient = await uow.patients.get(appointment.patient_id)
        phone = await self._contacts.phone(tenant_id, appointment.contact_id, Actor.system())
        payment = await self._payments.request(
            PaymentAsk(
                tenant_id=tenant_id,
                subject_type=SUBJECT,
                subject_id=appointment.id,
                contact_id=appointment.contact_id,
                payer_name=patient.full_name,
                payer_phone=phone,
                purpose=f"Consultation {appointment.reference}",
                amount_minor=policy.fee_minor,
            )
        )
        if payment.status != "pending":
            return  # already paid (the handler ran twice)
        prompt = await pay_prompt(
            self._payments,
            self._texts,
            tenant_id,
            payment.id,
            payment.amount_minor,
            appointment.reference,
        )
        fallback = TemplateFallback(
            "appointments.payment_due",
            (money(payment.amount_minor), appointment.reference),
            (f"rem:pay:{appointment.id}",),
        )
        if not await self._sender.notify(
            tenant_id, appointment.contact_id, prompt, fallback=fallback
        ):
            log.info("payment.prompt_skipped", extra={"appointment": str(appointment.id)})


class ExpireAppointmentPayment:
    def __init__(self, payments: Payments) -> None:
        self._payments = payments

    async def __call__(self, event: StoredEvent) -> None:
        if event.tenant_id is None:
            return
        await self._payments.expire(
            event.tenant_id, SUBJECT, [UUID(event.payload["appointment_id"])], Actor.system()
        )


class SendPaymentReceipt:
    def __init__(
        self,
        uow_for: Callable[[TenantId], AppointmentsUnitOfWork],
        sender: ChatSender,
        texts: Translator,
    ) -> None:
        self._uow_for, self._sender, self._texts = uow_for, sender, texts

    async def __call__(self, event: StoredEvent) -> None:
        key = RECEIPTS.get(event.event_type)
        p = event.payload
        if key is None or event.tenant_id is None or p.get("subject_type") != SUBJECT:
            return
        if not p.get("contact_id") or not p.get("subject_id"):
            return  # detached ledger entry: nobody to tell
        async with self._uow_for(event.tenant_id) as uow:
            try:
                appointment = await uow.appointments.get(UUID(p["subject_id"]))
            except AppointmentNotFoundError:
                return
        text = self._texts.t(
            key,
            amount=money(int(p["amount_minor"]), p.get("currency", "INR")),
            ref=appointment.reference,
            receipt=p.get("receipt_number", ""),
        )
        await self._sender.notify(
            event.tenant_id, UUID(p["contact_id"]), text, fallback=update_fallback(text)
        )


class DetachPayments:
    def __init__(self, payments: Payments) -> None:
        self._payments = payments

    async def __call__(self, event: StoredEvent) -> None:
        ids = [UUID(i) for i in event.payload.get("appointment_ids") or []]
        if event.tenant_id is not None and ids:
            await self._payments.detach(event.tenant_id, SUBJECT, ids)
