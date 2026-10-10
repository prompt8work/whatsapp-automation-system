from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.platform.inbox.domain.handover import Handover


class HandoverRepository(Protocol):
    """Tenant-scoped (RLS)."""

    async def active_for(self, contact_id: UUID) -> Handover | None: ...

    async def all_active(self) -> list[Handover]: ...

    async def add(self, handover: Handover) -> bool:
        """False if the contact already has an active handover (concurrent request)."""
        ...

    async def save(self, handover: Handover) -> None: ...
