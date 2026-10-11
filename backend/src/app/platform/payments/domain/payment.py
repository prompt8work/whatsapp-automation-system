"""Payment request and ledger entry (PRD PL-6.3 - PL-6.5, RT-7).

PENDING -> PAID | FAILED | EXPIRED,  PAID -> REFUNDED.
A payment the provider reports as paid AFTER it failed or expired is still accepted: the money
arrived, and the ledger must say so.

Once the record it was for is deleted by retention, the payment is DETACHED (subject = None) and
stays forever as a ledger entry with what the receipt showed: payer name and phone, amount,
dates, method and provider references - never health details (RT-7).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.platform.payments.domain.errors import InvalidPaymentTransitionError
from app.platform.payments.domain.events import (
    PaymentExpired,
    PaymentFailed,
    PaymentRefunded,
    PaymentRequested,
    PaymentSucceeded,
)
from app.shared.kernel.actor import Actor
from app.shared.kernel.entity import TenantAggregateRoot
from app.shared.kernel.ids import TenantId


class PaymentMethod(StrEnum):
    WHATSAPP_PAY = "whatsapp_pay"  # A: "Review and pay" inside WhatsApp
    RAZORPAY_LINK = "razorpay_link"  # B: a Razorpay payment link in the chat
    AT_CLINIC = "at_clinic"  # C: cash / UPI at the counter, staff mark it paid


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    EXPIRED = "expired"
    REFUNDED = "refunded"


S = PaymentStatus


def new_receipt_number() -> str:
    """Short, unambiguous, unique per tenant (checked by the database)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "RC-" + "".join(secrets.choice(alphabet) for _ in range(8))


@dataclass(kw_only=True, eq=False)
class PaymentRequest(TenantAggregateRoot):
    receipt_number: str
    subject_type: str | None  # e.g. "appointment"; None once detached (RT-7)
    subject_id: UUID | None
    contact_id: UUID | None
    payer_name: str  # as on the receipt (RT-7)
    payer_phone: str
    purpose: str  # e.g. "Consultation APT-4F2K" - never the reason for visit
    amount_minor: int  # paise
    currency: str
    method: PaymentMethod
    created_at: datetime
    expires_at: datetime | None = None
    status: PaymentStatus = PaymentStatus.PENDING
    gateway_ref: str | None = None  # Razorpay payment-link id / WhatsApp reference_id
    pay_url: str | None = None
    transaction_id: str | None = None  # Razorpay payment id / UPI transaction id
    paid_at: datetime | None = None
    refunded_at: datetime | None = None
    note: str = ""  # staff note on Mark as paid / refunded (e.g. "cash")

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: TenantId,
        subject_type: str,
        subject_id: UUID,
        contact_id: UUID | None,
        payer_name: str,
        payer_phone: str,
        purpose: str,
        amount_minor: int,
        currency: str,
        method: PaymentMethod,
        expires_at: datetime | None,
        at: datetime,
    ) -> PaymentRequest:
        if amount_minor <= 0:
            raise InvalidPaymentTransitionError("The amount must be more than zero")
        payment = cls(
            id=id,
            tenant_id=tenant_id,
            receipt_number=new_receipt_number(),
            subject_type=subject_type,
            subject_id=subject_id,
            contact_id=contact_id,
            payer_name=payer_name[:120],
            payer_phone=payer_phone,
            purpose=purpose[:120],
            amount_minor=amount_minor,
            currency=currency,
            method=method,
            created_at=at,
            expires_at=expires_at,
        )
        payment.record(
            PaymentRequested(
                occurred_at=at,
                payment_id=id,
                subject_type=subject_type,
                subject_id=subject_id,
                amount_minor=amount_minor,
                method=method.value,
            )
        )
        return payment

    @property
    def is_settled(self) -> bool:
        """RT-6: only a PENDING payment blocks the retention purge."""
        return self.status is not PaymentStatus.PENDING

    def attach_gateway(self, gateway_ref: str | None, pay_url: str | None) -> None:
        self.gateway_ref, self.pay_url = gateway_ref, pay_url

    def mark_paid(
        self, *, actor: Actor, at: datetime, transaction_id: str | None = None, note: str = ""
    ) -> bool:
        """False (no change) if it is already paid - webhooks arrive more than once."""
        if self.status in (S.PAID, S.REFUNDED):
            return False
        self.status, self.paid_at = S.PAID, at
        self.transaction_id = transaction_id or self.transaction_id
        self.note = note.strip()[:200] or self.note
        self.record(
            PaymentSucceeded(
                occurred_at=at,
                payment_id=self.id,
                subject_type=self.subject_type,
                subject_id=self.subject_id,
                contact_id=self.contact_id,
                amount_minor=self.amount_minor,
                currency=self.currency,
                receipt_number=self.receipt_number,
                actor=actor,
            )
        )
        return True

    def mark_failed(self, *, at: datetime) -> bool:
        if self.status is not S.PENDING:
            return False
        self.status = S.FAILED
        self.record(
            PaymentFailed(
                occurred_at=at,
                payment_id=self.id,
                subject_type=self.subject_type,
                subject_id=self.subject_id,
            )
        )
        return True

    def expire(self, *, actor: Actor, at: datetime) -> bool:
        """No longer due (expired link, or the appointment ended unpaid - PL-6.5)."""
        if self.status is not S.PENDING:
            return False
        self.status = S.EXPIRED
        self.record(
            PaymentExpired(
                occurred_at=at,
                payment_id=self.id,
                subject_type=self.subject_type,
                subject_id=self.subject_id,
                actor=actor,
            )
        )
        return True

    def mark_refunded(self, *, actor: Actor, at: datetime, note: str = "") -> bool:
        if self.status is S.REFUNDED:
            return False
        if self.status is not S.PAID:
            raise InvalidPaymentTransitionError("Only a paid payment can be refunded")
        self.status, self.refunded_at = S.REFUNDED, at
        self.note = note.strip()[:200] or self.note
        self.record(
            PaymentRefunded(
                occurred_at=at,
                payment_id=self.id,
                subject_type=self.subject_type,
                subject_id=self.subject_id,
                contact_id=self.contact_id,
                amount_minor=self.amount_minor,
                actor=actor,
            )
        )
        return True

    def detach(self) -> None:
        """RT-7: the record it was for is gone; keep the payment as a ledger entry."""
        self.subject_type, self.subject_id, self.contact_id = None, None, None


@dataclass(frozen=True)
class PaymentSettings:
    """A clinic's payment setup (PL-6.1, PL-6.2). Secrets live in the credential store."""

    methods: tuple[PaymentMethod, ...] = ()
    whatsapp_pay_configuration: str = ""  # name set up in WhatsApp Business Manager
    razorpay_key_id: str = ""
    currency: str = "INR"

    @property
    def primary_method(self) -> PaymentMethod | None:
        """What the patient is offered: in-chat payment first, then a link, then the counter.
        Whatever is offered, staff can always Mark as paid at the clinic."""
        for method in PaymentMethod:
            if method in self.methods:
                return method
        return None
