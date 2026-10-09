from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.platform.conversations.domain.session import ConversationSession


class SessionRepository(Protocol):
    """Tenant-scoped (RLS)."""

    async def lock_and_get(self, contact_id: UUID) -> ConversationSession | None:
        """Serialise processing per contact for the rest of the transaction (PL-3.2 LockSession):
        two quick messages from one person are handled one after the other, never in parallel."""
        ...

    async def save(self, session: ConversationSession) -> None:
        """Insert or update."""
        ...
