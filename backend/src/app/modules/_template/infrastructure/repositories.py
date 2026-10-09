"""SQL implementation of `ItemRepository`.

- Every loaded/added aggregate is `track`ed so the Unit of Work saves its events.
- `save` uses optimistic locking: UPDATE ... WHERE version = <loaded version>.
- No `tenant_id` filter needed: RLS (set by the Unit of Work) already restricts rows.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules._template.domain.errors import ItemNotFoundError
from app.modules._template.domain.item import Item
from app.modules._template.infrastructure.mappers import item_from_row, item_to_row
from app.modules._template.infrastructure.tables import template_items
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.kernel.errors import ConcurrencyConflictError


class SqlItemRepository:
    def __init__(self, session: AsyncSession, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    async def get(self, item_id: UUID) -> Item:
        result = await self._session.execute(
            select(template_items).where(template_items.c.id == item_id)
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ItemNotFoundError()
        item = item_from_row(row)
        self._uow.track(item)
        return item

    async def add(self, item: Item) -> None:
        await self._session.execute(insert(template_items).values(item_to_row(item)))
        self._uow.track(item)

    async def save(self, item: Item) -> None:
        values = item_to_row(item) | {"version": item.version + 1}
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(template_items)
                .where(template_items.c.id == item.id, template_items.c.version == item.version)
                .values(values)
            ),
        )
        if result.rowcount != 1:
            raise ConcurrencyConflictError()
        item.version += 1
        self._uow.track(item)
