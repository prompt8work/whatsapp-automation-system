"""Query: get one item. Queries never change state and never commit.

Simple queries reuse the repository. Screens that need joins or aggregates get a
dedicated `...ReadModel` Protocol with optimised SQL instead (ARCHITECTURE §6.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.modules._template.application.dto import ItemDTO
from app.modules._template.application.unit_of_work import TemplateUnitOfWork


@dataclass(frozen=True)
class GetItemQuery:
    item_id: UUID


class GetItem:
    def __init__(self, uow: TemplateUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, query: GetItemQuery) -> ItemDTO:
        async with self._uow as uow:
            item = await uow.items.get(query.item_id)
        return ItemDTO.from_domain(item)
