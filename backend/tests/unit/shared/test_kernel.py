"""Shared kernel building blocks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from app.shared.infrastructure.serialization import serialize_event
from app.shared.kernel.actor import Actor
from app.shared.kernel.entity import TenantAggregateRoot
from app.shared.kernel.events import DomainEvent
from app.shared.kernel.ids import TenantId, uuid7

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


def test_uuid7_has_version_7_and_is_time_ordered() -> None:
    ids = [uuid7() for _ in range(50)]

    assert all(i.version == 7 for i in ids)
    assert all(i.variant == "specified in RFC 4122" for i in ids)
    # Same-millisecond ids may tie on timestamp; compare the 48-bit time prefix only.
    prefixes = [i.int >> 80 for i in ids]
    assert prefixes == sorted(prefixes)


@dataclass(frozen=True, kw_only=True)
class SomethingHappened(DomainEvent):
    thing_id: UUID


@dataclass(kw_only=True, eq=False)
class Thing(TenantAggregateRoot):
    def do(self) -> None:
        self.record(SomethingHappened(occurred_at=NOW, thing_id=self.id))


def test_pull_events_returns_and_clears() -> None:
    thing = Thing(id=UUID(int=1), tenant_id=TenantId(UUID(int=9)))
    thing.do()

    assert [e.event_type for e in thing.pull_events()] == ["SomethingHappened"]
    assert thing.pull_events() == []


def test_aggregates_are_equal_by_id() -> None:
    tenant = TenantId(UUID(int=9))
    assert Thing(id=UUID(int=1), tenant_id=tenant) == Thing(id=UUID(int=1), tenant_id=tenant)


class Colour(StrEnum):
    RED = "red"


@dataclass(frozen=True, kw_only=True)
class RichEvent(DomainEvent):
    actor: Actor
    colour: Colour
    tags: tuple[str, ...]


def test_serialize_event_is_json_safe() -> None:
    event = RichEvent(
        occurred_at=NOW,
        event_id=UUID(int=5),
        actor=Actor.staff(UUID(int=7)),
        colour=Colour.RED,
        tags=("a", "b"),
    )

    assert serialize_event(event) == {
        "occurred_at": "2026-10-10T09:00:00+00:00",
        "event_id": "00000000-0000-0000-0000-000000000005",
        "actor": {"kind": "staff", "id": "00000000-0000-0000-0000-000000000007"},
        "colour": "red",
        "tags": ["a", "b"],
    }
