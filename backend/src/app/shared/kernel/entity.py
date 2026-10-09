"""Aggregate root base classes.

Rules for every aggregate (ARCHITECTURE §5.1):
- state changes ONLY through methods named after business actions (`approve`, `rename`),
  never through setters;
- every change records a `DomainEvent`;
- `version` is used for optimistic locking by the repository.

Use `TenantAggregateRoot` for anything that belongs to one tenant (almost everything) and
plain `AggregateRoot` only for platform-level records (users, tenants, scheduled jobs).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.shared.kernel.events import DomainEvent
from app.shared.kernel.ids import TenantId


@dataclass(kw_only=True, eq=False)
class AggregateRoot:
    id: UUID
    version: int = 0
    _events: list[DomainEvent] = field(default_factory=list, repr=False, compare=False)

    def record(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events, self._events = self._events, []
        return events

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass(kw_only=True, eq=False)
class TenantAggregateRoot(AggregateRoot):
    tenant_id: TenantId
