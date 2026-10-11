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
class TemplateSlot:
    """A message a module may need to send OUTSIDE the 24 h window (PRD PL-4.2). Each clinic
    maps the slot to one of its Meta-approved templates (Settings → WhatsApp templates)."""

    key: str  # e.g. "appointments.reminder"
    description: str  # what the template is for, shown to the clinic
    params: tuple[str, ...] = ()  # body variables {{1}}, {{2}} ... in this order
    buttons: tuple[str, ...] = ()  # quick-reply buttons, in this order
    example: str = ""  # suggested body text for the clinic to submit to Meta


@dataclass(frozen=True)
class TemplateFallback:
    """What to send instead when the contact is outside the 24 h window."""

    slot: str
    params: tuple[str, ...] = ()
    button_payloads: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Meta rejects variables with new lines, tabs or more than 4 spaces in a row.
        object.__setattr__(
            self, "params", tuple(" ".join(p.split())[:1000] or "-" for p in self.params)
        )


@dataclass(frozen=True)
class SendRequest:
    tenant_id: TenantId
    contact_id: UUID
    to: str  # recipient phone, E.164 ("+9198...") or wa_id
    phone_number_id: str  # which of the tenant's WhatsApp numbers sends it
    message: OutboundMessage
    last_inbound_at: datetime | None  # the contact's last message, for the 24 h window
    # Outside the window, send the clinic's template for this slot instead (if it mapped one).
    fallback: TemplateFallback | None = None


@dataclass(frozen=True)
class SendReceipt:
    message_id: UUID
    sent: bool  # False: failed (a transient failure is retried automatically)


class Messenger(Protocol):
    async def send(self, request: SendRequest) -> SendReceipt:
        """After 24 h: sends the fallback template if the clinic mapped one, otherwise raises
        OutsideServiceWindowError."""
        ...
