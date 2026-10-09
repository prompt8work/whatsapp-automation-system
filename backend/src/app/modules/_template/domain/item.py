"""The `Item` aggregate - the pattern every aggregate follows.

- Construct new instances with the `create` factory (validates + records the first event).
- Change state only through business methods (`rename`), each recording an event.
- No I/O, no clock, no id generation: those come in as arguments.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules._template.domain.errors import InvalidItemNameError, ItemNameUnchangedError
from app.modules._template.domain.events import ItemCreated, ItemRenamed
from app.shared.kernel.actor import Actor
from app.shared.kernel.entity import TenantAggregateRoot
from app.shared.kernel.ids import TenantId

MAX_NAME_LENGTH = 100


def _valid_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > MAX_NAME_LENGTH:
        raise InvalidItemNameError(f"Name must be 1-{MAX_NAME_LENGTH} characters")
    return cleaned


@dataclass(kw_only=True, eq=False)
class Item(TenantAggregateRoot):
    name: str
    created_at: datetime

    @classmethod
    def create(
        cls, *, id: UUID, tenant_id: TenantId, name: str, actor: Actor, at: datetime
    ) -> Item:
        item = cls(id=id, tenant_id=tenant_id, name=_valid_name(name), created_at=at)
        item.record(ItemCreated(occurred_at=at, item_id=id, name=item.name, actor=actor))
        return item

    def rename(self, new_name: str, *, actor: Actor, at: datetime) -> None:
        new_name = _valid_name(new_name)
        if new_name == self.name:
            raise ItemNameUnchangedError()
        old_name, self.name = self.name, new_name
        self.record(
            ItemRenamed(
                occurred_at=at,
                item_id=self.id,
                old_name=old_name,
                new_name=new_name,
                actor=actor,
            )
        )
