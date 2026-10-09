"""Use-case tests with fakes: real business flow, no database."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.modules._template.application.commands.create_item import CreateItem, CreateItemCommand
from app.modules._template.application.commands.rename_item import RenameItem, RenameItemCommand
from app.modules._template.application.queries.get_item import GetItem, GetItemQuery
from app.modules._template.domain.errors import ItemNotFoundError
from app.modules._template.domain.events import ItemCreated, ItemRenamed
from app.modules._template.tests.fakes import InMemoryTemplateUnitOfWork
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.testing.fakes import FixedClock, SequentialIds

TENANT = TenantId(UUID(int=100))
ACTOR = Actor.system()


@pytest.fixture
def uow() -> InMemoryTemplateUnitOfWork:
    return InMemoryTemplateUnitOfWork()


async def test_create_then_rename_commits_both_events(uow: InMemoryTemplateUnitOfWork) -> None:
    clock = FixedClock()
    created = await CreateItem(uow, clock, SequentialIds(), TENANT)(
        CreateItemCommand(name="Draft", actor=ACTOR)
    )

    renamed = await RenameItem(uow, clock)(
        RenameItemCommand(item_id=created.id, new_name="Final", actor=ACTOR)
    )

    assert renamed.name == "Final"
    assert renamed.version == created.version + 1
    assert [type(e) for e in uow.committed_events] == [ItemCreated, ItemRenamed]
    assert uow.commits == 2


async def test_get_unknown_item_raises_not_found(uow: InMemoryTemplateUnitOfWork) -> None:
    with pytest.raises(ItemNotFoundError):
        await GetItem(uow)(GetItemQuery(item_id=UUID(int=999)))
