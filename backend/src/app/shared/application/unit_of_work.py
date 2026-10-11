"""Unit of Work port (ARCHITECTURE §6.2).

A use case opens ONE Unit of Work, loads aggregates through its repositories, calls
business methods, and commits. On commit the implementation:

1. pulls events from every tracked aggregate,
2. writes them to the outbox (and module history tables),
3. commits the database transaction.

A Unit of Work is always scoped to ONE tenant, so repositories never take a tenant
parameter and cannot accidentally read another tenant's data.

Each module declares its own Protocol that extends this one with its repositories:

    class AppointmentsUnitOfWork(UnitOfWork, Protocol):
        appointments: AppointmentRepository
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self

from app.shared.kernel.entity import AggregateRoot


class UnitOfWork(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def track(self, aggregate: AggregateRoot) -> None:
        """Remember an aggregate so its events are saved on commit. Repositories call this."""
        ...

    def touch(self, topic: str) -> None:
        """Mark a dashboard topic as changed by this unit of work (live updates, §8.9)."""
        ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
