"""Messenger port: how ANY module sends a WhatsApp message (PRD PL-4.1).

    receipt = await services.messenger.send(SendRequest(tenant_id, contact.id, contact.phone,
                                                        phone_number_id, Text("Hi!"),
                                                        contact.last_inbound_at))

The platform's messaging module implements it: it enforces the 24-hour window, logs the
message, sends through Meta (or the local recorder) and retries transient failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.shared.kernel.errors import DomainError
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import OutboundMessage


class OutsideServiceWindowError(DomainError):
    """Free-form messages are only allowed within 24 h of the contact's last message;
    after that only approved Templates (PRD PL-4.2)."""

    code = "messaging.outside_window"


@dataclass(frozen=True)
class SendRequest:
    tenant_id: TenantId
    contact_id: UUID
    to: str  # recipient phone, E.164 ("+9198...") or wa_id
    phone_number_id: str  # which of the tenant's WhatsApp numbers sends it
    message: OutboundMessage
    last_inbound_at: datetime | None  # the contact's last message, for the 24 h window


@dataclass(frozen=True)
class SendReceipt:
    message_id: UUID
    sent: bool  # False: failed (a transient failure is retried automatically)


class Messenger(Protocol):
    async def send(self, request: SendRequest) -> SendReceipt:
        """Raises OutsideServiceWindowError for non-template messages after 24 h."""
        ...
