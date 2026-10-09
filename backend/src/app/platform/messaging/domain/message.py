"""The message log: every WhatsApp message in or out (PRD PL-4.3, PL-4.4).

Operational records, not business events: there are many and they change fast, so they
record no domain events. The staff inbox (step 6) reads this log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.platform.messaging.domain.inbound import DeliveryStatus
from app.shared.kernel.entity import TenantAggregateRoot
from app.shared.kernel.ids import TenantId


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(StrEnum):
    # inbound
    RECEIVED = "received"
    PROCESSED = "processed"
    # outbound
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


# Delivery receipts can arrive out of order; never move backwards.
_RANK = {
    MessageStatus.QUEUED: 0,
    MessageStatus.SENT: 1,
    MessageStatus.DELIVERED: 2,
    MessageStatus.READ: 3,
    MessageStatus.FAILED: 4,
}


@dataclass(kw_only=True, eq=False)
class Message(TenantAggregateRoot):
    contact_id: UUID
    direction: Direction
    content: dict[str, Any]
    status: MessageStatus
    created_at: datetime
    phone_number_id: str
    wa_message_id: str | None = None
    error: str | None = None
    attempts: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def inbound(
        cls,
        *,
        id: UUID,
        tenant_id: TenantId,
        contact_id: UUID,
        phone_number_id: str,
        wa_message_id: str,
        content: dict[str, Any],
        at: datetime,
    ) -> Message:
        return cls(
            id=id,
            tenant_id=tenant_id,
            contact_id=contact_id,
            direction=Direction.INBOUND,
            content=content,
            status=MessageStatus.RECEIVED,
            created_at=at,
            phone_number_id=phone_number_id,
            wa_message_id=wa_message_id,
        )

    @classmethod
    def outbound(
        cls,
        *,
        id: UUID,
        tenant_id: TenantId,
        contact_id: UUID,
        phone_number_id: str,
        content: dict[str, Any],
        at: datetime,
    ) -> Message:
        return cls(
            id=id,
            tenant_id=tenant_id,
            contact_id=contact_id,
            direction=Direction.OUTBOUND,
            content=content,
            status=MessageStatus.QUEUED,
            created_at=at,
            phone_number_id=phone_number_id,
        )

    def mark_processed(self) -> None:
        self.status = MessageStatus.PROCESSED

    def mark_sent(self, wa_message_id: str) -> None:
        """Accepted by Meta. Set directly (not via _advance): a successful RETRY must leave
        FAILED, otherwise the retry job would resend it forever."""
        self.attempts += 1
        self.wa_message_id = wa_message_id
        self.error = None
        self.status = MessageStatus.SENT

    def mark_send_failed(self, error: str) -> None:
        self.attempts += 1
        self.error = error[:500]
        self.status = MessageStatus.FAILED

    def apply_delivery_status(self, status: DeliveryStatus, error: str | None = None) -> None:
        if status is DeliveryStatus.FAILED:
            self.error = (error or "delivery failed")[:500]
        self._advance(MessageStatus(status.value))

    def _advance(self, status: MessageStatus) -> None:
        if _RANK[status] >= _RANK.get(self.status, 0):
            self.status = status
