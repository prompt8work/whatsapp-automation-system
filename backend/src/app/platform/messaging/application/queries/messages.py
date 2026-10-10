"""Reading the message log - for the staff inbox (PRD PL-4.4, PL-5.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class MessageView:
    id: UUID
    contact_id: UUID
    direction: str  # "inbound" | "outbound"
    text: str
    status: str
    created_at: datetime
    error: str | None = None


class MessageReadModel(Protocol):
    """Tenant-scoped (RLS)."""

    async def latest_per_contact(self, limit: int) -> list[MessageView]:
        """The newest message of each conversation, newest conversations first."""
        ...

    async def thread(self, contact_id: UUID, limit: int) -> list[MessageView]:
        """The last `limit` messages with one contact, oldest first."""
        ...

    async def last_inbound_at(self, contact_ids: list[UUID]) -> dict[UUID, datetime]: ...


class ListConversations:
    def __init__(self, reads: MessageReadModel) -> None:
        self._reads = reads

    async def __call__(self, limit: int = 50) -> list[MessageView]:
        return await self._reads.latest_per_contact(max(1, min(limit, 200)))


class GetThread:
    def __init__(self, reads: MessageReadModel) -> None:
        self._reads = reads

    async def __call__(self, contact_id: UUID, limit: int = 100) -> list[MessageView]:
        return await self._reads.thread(contact_id, max(1, min(limit, 500)))
