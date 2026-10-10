"""What the inbox needs from other modules (adapted in inbox/wiring.py)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId


@dataclass(frozen=True)
class MessageLine:
    id: UUID
    contact_id: UUID
    direction: str  # "inbound" | "outbound"
    text: str
    status: str
    created_at: datetime
    error: str | None = None


@dataclass(frozen=True)
class ContactCard:
    id: UUID
    phone: str
    profile_name: str | None
    last_inbound_at: datetime | None
    is_opted_out: bool


class InboxMessages(Protocol):
    async def latest_per_contact(self, tenant_id: TenantId, limit: int) -> list[MessageLine]: ...

    async def thread(
        self, tenant_id: TenantId, contact_id: UUID, limit: int
    ) -> list[MessageLine]: ...


class InboxContacts(Protocol):
    """Reads are audited by the contacts module."""

    async def cards(
        self, tenant_id: TenantId, contact_ids: list[UUID], actor: Actor
    ) -> dict[UUID, ContactCard]: ...


class StaffSender(Protocol):
    async def send_text(self, tenant_id: TenantId, contact: ContactCard, text: str) -> bool:
        """Raises OutsideServiceWindowError more than 24 h after the contact's last message."""
        ...
