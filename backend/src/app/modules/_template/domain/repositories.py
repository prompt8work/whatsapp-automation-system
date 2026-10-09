"""Repository ports (Protocols). Implemented in infrastructure/, faked in tests/.

No tenant parameter: the Unit of Work is already scoped to one tenant.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.modules._template.domain.item import Item


class ItemRepository(Protocol):
    async def get(self, item_id: UUID) -> Item:
        """Raises ItemNotFoundError."""
        ...

    async def add(self, item: Item) -> None: ...

    async def save(self, item: Item) -> None:
        """Raises ConcurrencyConflictError if someone else saved it first."""
        ...
