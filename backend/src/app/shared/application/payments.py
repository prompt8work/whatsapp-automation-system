"""Payments port for feature modules (PRD §6.6) - like Messenger, provided by the platform.

    info = await services.payments.request(PaymentAsk(tenant, "appointment", appt.id, ...))
    message = await services.payments.pay_message(tenant, info.id, body, "Pay now")

`platform/payments` implements it; modules never see gateways, keys or webhooks.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import OutboundMessage


@dataclass(frozen=True)
class PaymentAsk:
    tenant_id: TenantId
    subject_type: str  # e.g. "appointment"
    subject_id: UUID
    contact_id: UUID | None
    payer_name: str  # printed on the receipt; kept in the ledger (RT-7)
    payer_phone: str
    purpose: str  # e.g. "Consultation APT-4F2K" - never health details
    amount_minor: int  # paise
    expires_at: datetime | None = None


@dataclass(frozen=True)
class PaymentInfo:
    id: UUID
    receipt_number: str
    subject_id: UUID | None
    amount_minor: int
    currency: str
    method: str  # "whatsapp_pay" | "razorpay_link" | "at_clinic"
    status: str  # "pending" | "paid" | "failed" | "expired" | "refunded"
    pay_url: str | None
    paid_at: datetime | None


class Payments(Protocol):
    async def primary_method(self, tenant_id: TenantId) -> str | None:
        """What patients are offered; None = the clinic has payments switched off."""
        ...

    async def request(self, ask: PaymentAsk) -> PaymentInfo:
        """Creates the payment, or returns the live (pending/paid) one for that record."""
        ...

    async def pay_message(
        self, tenant_id: TenantId, payment_id: UUID, body: str, button: str
    ) -> OutboundMessage | None:
        """What the patient taps to pay. None: pay at clinic, or no longer pending."""
        ...

    async def for_subjects(
        self, tenant_id: TenantId, subject_type: str, subject_ids: Collection[UUID]
    ) -> list[PaymentInfo]: ...

    async def unsettled(
        self, tenant_id: TenantId, subject_type: str, subject_ids: Collection[UUID]
    ) -> set[UUID]:
        """Records with a PENDING payment - they block the retention purge (RT-6)."""
        ...

    async def expire(
        self, tenant_id: TenantId, subject_type: str, subject_ids: Collection[UUID], actor: Actor
    ) -> int:
        """The records ended unpaid (cancelled, declined, no-show ...) (PL-6.5)."""
        ...

    async def detach(
        self, tenant_id: TenantId, subject_type: str, subject_ids: Collection[UUID]
    ) -> int:
        """The records were deleted; their payments stay as ledger entries (RT-7)."""
        ...
