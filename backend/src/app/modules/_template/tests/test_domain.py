"""Domain unit tests: pure Python, no I/O, milliseconds."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.modules._template.domain.errors import InvalidItemNameError, ItemNameUnchangedError
from app.modules._template.domain.events import ItemCreated, ItemRenamed
from app.modules._template.domain.item import Item
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.testing.fakes import FixedClock

TENANT = TenantId(UUID(int=100))
ACTOR = Actor.system()
NOW = FixedClock().now()


def make_item(name: str = "First") -> Item:
    return Item.create(id=UUID(int=1), tenant_id=TENANT, name=name, actor=ACTOR, at=NOW)


def test_create_normalises_whitespace_and_records_event() -> None:
    item = make_item("  Hello   world ")

    assert item.name == "Hello world"
    [event] = item.pull_events()
    assert isinstance(event, ItemCreated)
    assert event.name == "Hello world"


@pytest.mark.parametrize("bad", ["", "   ", "x" * 101])
def test_create_rejects_invalid_names(bad: str) -> None:
    with pytest.raises(InvalidItemNameError):
        make_item(bad)


def test_rename_records_old_and_new_name() -> None:
    item = make_item("Old")
    item.pull_events()

    item.rename("New", actor=ACTOR, at=NOW)

    [event] = item.pull_events()
    assert isinstance(event, ItemRenamed)
    assert (event.old_name, event.new_name) == ("Old", "New")


def test_rename_to_same_name_is_rejected() -> None:
    item = make_item("Same")
    with pytest.raises(ItemNameUnchangedError):
        item.rename("Same", actor=ACTOR, at=NOW)
