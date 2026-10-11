"""Payment events. Ids and amounts only - no names, phones or reasons for visit."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.shared.kernel.actor import Actor
from app.shared.kernel.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class PaymentEvent(DomainEvent):
    """Every payment event is also a row of the payment's history (PL-6.5)."""

    payment_id: UUID
    subject_type: str | None
    subject_id: UUID | None


@dataclass(frozen=True, kw_only=True)
class PaymentRequested(PaymentEvent):
    amount_minor: int
    method: str


@dataclass(frozen=True, kw_only=True)
class PaymentSucceeded(PaymentEvent):
    contact_id: UUID | None
    amount_minor: int
    currency: str
    receipt_number: str
    actor: Actor  # system (webhook) or the staff member who marked it paid


@dataclass(frozen=True, kw_only=True)
class PaymentFailed(PaymentEvent):
    pass


@dataclass(frozen=True, kw_only=True)
class PaymentExpired(PaymentEvent):
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class PaymentRefunded(PaymentEvent):
    contact_id: UUID | None
    amount_minor: int
    actor: Actor
