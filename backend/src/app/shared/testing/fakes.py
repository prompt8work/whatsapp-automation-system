"""Deterministic fakes for tests. They honour the same Protocols as production adapters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self
from uuid import UUID

from app.shared.kernel.entity import AggregateRoot
from app.shared.kernel.events import DomainEvent


class FixedClock:
    def __init__(self, at: datetime | None = None) -> None:
        self._now = at or datetime(2026, 10, 9, 9, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


class SequentialIds:
    """Ids 00000000-0000-0000-0000-000000000001, ...02, ... - easy to read in assertions."""

    def __init__(self) -> None:
        self._next = 1

    def new_id(self) -> UUID:
        value = UUID(int=self._next)
        self._next += 1
        return value


class InMemoryUnitOfWork:
    """Base for module fakes. Keeps committed events in `committed_events` for assertions."""

    def __init__(self) -> None:
        self._tracked: list[AggregateRoot] = []
        self.committed_events: list[DomainEvent] = []
        self.commits = 0

    async def __aenter__(self) -> Self:
        self._tracked = []
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._tracked = []

    def track(self, aggregate: AggregateRoot) -> None:
        if aggregate not in self._tracked:
            self._tracked.append(aggregate)

    async def commit(self) -> None:
        for aggregate in self._tracked:
            self.committed_events.extend(aggregate.pull_events())
        self.commits += 1

    async def rollback(self) -> None:
        self._tracked = []
