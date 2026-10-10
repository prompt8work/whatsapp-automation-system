"""SQLAlchemy Unit of Work with tenant isolation (ARCHITECTURE §6.2, §8.2).

Opening the Unit of Work starts a transaction and runs
`set_config('app.tenant_id', <tenant>, true)` - the parameterised form of `SET LOCAL`.
Row-level-security policies read that setting, so even a buggy query cannot see another
tenant's rows. It lasts only for this transaction, which makes it safe behind a
transaction-mode connection pooler.

Modules subclass this and create their repositories in `_create_repositories()`:

    class SqlAppointmentsUnitOfWork(SqlUnitOfWork):
        def _create_repositories(self) -> None:
            self.appointments = SqlAppointmentRepository(self.session, self)
"""

from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.infrastructure.serialization import serialize_event
from app.shared.infrastructure.tables import outbox
from app.shared.kernel.entity import AggregateRoot
from app.shared.kernel.events import DomainEvent
from app.shared.kernel.ids import TenantId


class SqlUnitOfWork:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        tenant_id: TenantId | None,
    ) -> None:
        self._session_factory = session_factory
        self._tenant_id = tenant_id
        self._session: AsyncSession | None = None
        self._tracked: list[AggregateRoot] = []
        self._published: list[DomainEvent] = []

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Unit of Work used outside `async with`")
        return self._session

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self._tracked, self._published = [], []
        await self._session.begin()
        # Timestamps read back in UTC whatever the server's default timezone is (ARCH §13:
        # "store and process UTC"). Transaction-scoped, so safe behind a pooler.
        await self._session.execute(text("SELECT set_config('TimeZone', 'UTC', true)"))
        if self._tenant_id is not None:
            await self._session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(self._tenant_id)},
            )
        self._create_repositories()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self.session
        if session.in_transaction():  # not committed -> roll back (also on exceptions)
            await session.rollback()
        await session.close()
        self._session = None

    def _create_repositories(self) -> None:
        """Override in module Units of Work."""

    def track(self, aggregate: AggregateRoot) -> None:
        if aggregate not in self._tracked:
            self._tracked.append(aggregate)

    def publish(self, event: DomainEvent) -> None:
        """An event with no aggregate to carry it (e.g. a purge: the aggregate is gone)."""
        self._published.append(event)

    async def commit(self) -> None:
        events: list[DomainEvent] = list(self._published)
        for aggregate in self._tracked:
            events.extend(aggregate.pull_events())
        await self._save_events(events)
        await self.session.commit()
        self._tracked, self._published = [], []

    async def rollback(self) -> None:
        await self.session.rollback()
        self._tracked, self._published = [], []

    async def _save_events(self, events: list[DomainEvent]) -> None:
        """Write events to the outbox. Modules with a history table extend this."""
        if not events:
            return
        await self.session.execute(
            insert(outbox),
            [
                {
                    "id": event.event_id,
                    "tenant_id": self._tenant_id,
                    "event_type": event.event_type,
                    "payload": serialize_event(event),
                    "occurred_at": event.occurred_at,
                }
                for event in events
            ],
        )
