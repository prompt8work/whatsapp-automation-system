"""In-memory implementations of this module's ports. They must behave like the SQL ones."""

from __future__ import annotations

import copy
from uuid import UUID

from app.modules._template.domain.errors import ItemNotFoundError
from app.modules._template.domain.item import Item
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.kernel.errors import ConcurrencyConflictError
from app.shared.testing.fakes import InMemoryUnitOfWork


def _snapshot(item: Item) -> Item:
    """Copy without pending events - like a database row, which never stores them."""
    stored = copy.deepcopy(item)
    stored.pull_events()
    return stored


class InMemoryItemRepository:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self.rows: dict[UUID, Item] = {}

    async def get(self, item_id: UUID) -> Item:
        if item_id not in self.rows:
            raise ItemNotFoundError()
        item = _snapshot(self.rows[item_id])
        self._uow.track(item)
        return item

    async def add(self, item: Item) -> None:
        self.rows[item.id] = _snapshot(item)
        self._uow.track(item)

    async def save(self, item: Item) -> None:
        if self.rows[item.id].version != item.version:
            raise ConcurrencyConflictError()
        item.version += 1
        self.rows[item.id] = _snapshot(item)
        self._uow.track(item)


class InMemoryTemplateUnitOfWork(InMemoryUnitOfWork):
    def __init__(self) -> None:
        super().__init__()
        self.items = InMemoryItemRepository(self)
