"""Use case: rename an item (load -> business method -> save -> commit)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.modules._template.application.dto import ItemDTO
from app.modules._template.application.unit_of_work import TemplateUnitOfWork
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock


@dataclass(frozen=True)
class RenameItemCommand:
    item_id: UUID
    new_name: str
    actor: Actor


class RenameItem:
    def __init__(self, uow: TemplateUnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def __call__(self, cmd: RenameItemCommand) -> ItemDTO:
        async with self._uow as uow:
            item = await uow.items.get(cmd.item_id)
            item.rename(cmd.new_name, actor=cmd.actor, at=self._clock.now())
            await uow.items.save(item)
            await uow.commit()
        return ItemDTO.from_domain(item)
