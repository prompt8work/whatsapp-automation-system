"""Data returned by use cases. Use cases never return domain objects to callers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules._template.domain.item import Item


@dataclass(frozen=True)
class ItemDTO:
    id: UUID
    name: str
    created_at: datetime
    version: int

    @classmethod
    def from_domain(cls, item: Item) -> ItemDTO:
        return cls(id=item.id, name=item.name, created_at=item.created_at, version=item.version)
