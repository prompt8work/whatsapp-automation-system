"""Use case: create an item. The pattern every command follows (ARCHITECTURE §6.1).

1. A frozen `...Command` dataclass is the input.
2. The use case class receives its dependencies (Protocols) in `__init__`.
3. `__call__` opens the Unit of Work, calls domain methods, commits, returns a DTO.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules._template.application.dto import ItemDTO
from app.modules._template.application.unit_of_work import TemplateUnitOfWork
from app.modules._template.domain.item import Item
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId


@dataclass(frozen=True)
class CreateItemCommand:
    name: str
    actor: Actor


class CreateItem:
    def __init__(
        self, uow: TemplateUnitOfWork, clock: Clock, ids: IdGenerator, tenant_id: TenantId
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._tenant_id = tenant_id

    async def __call__(self, cmd: CreateItemCommand) -> ItemDTO:
        async with self._uow as uow:
            item = Item.create(
                id=self._ids.new_id(),
                tenant_id=self._tenant_id,
                name=cmd.name,
                actor=cmd.actor,
                at=self._clock.now(),
            )
            await uow.items.add(item)
            await uow.commit()
        return ItemDTO.from_domain(item)
