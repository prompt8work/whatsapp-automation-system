from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.platform.payments.domain.payment import PaymentRequest


@dataclass(frozen=True)
class PaymentDTO:
    id: UUID
    receipt_number: str
    subject_type: str | None
    subject_id: UUID | None
    contact_id: UUID | None
    payer_name: str
    payer_phone: str
    purpose: str
    amount_minor: int
    currency: str
    method: str
    status: str
    created_at: datetime
    expires_at: datetime | None
    pay_url: str | None
    transaction_id: str | None
    paid_at: datetime | None
    refunded_at: datetime | None
    note: str

    @classmethod
    def from_domain(cls, p: PaymentRequest) -> PaymentDTO:
        return cls(
            p.id,
            p.receipt_number,
            p.subject_type,
            p.subject_id,
            p.contact_id,
            p.payer_name,
            p.payer_phone,
            p.purpose,
            p.amount_minor,
            p.currency,
            p.method.value,
            p.status.value,
            p.created_at,
            p.expires_at,
            p.pay_url,
            p.transaction_id,
            p.paid_at,
            p.refunded_at,
            p.note,
        )
