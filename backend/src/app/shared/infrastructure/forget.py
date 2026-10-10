"""ContactForgotten handler (retention RT-4): delete this module's rows for the contact.

A platform module that keeps rows per contact WITHOUT a foreign key to contacts (message log,
conversation session, handovers) registers one of these in its ModuleDefinition:

    event_handlers={"ContactForgotten": [forget_rows_in(messages)]}

(Tables WITH a foreign key to contacts keep the contact alive instead - see the contacts purger.)
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Table, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.application.events import EventHandler, StoredEvent
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork
from app.shared.module import EventHandlerFactory, PlatformServices

CONTACT_FORGOTTEN = "ContactForgotten"


class DeleteContactRows:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], table: Table) -> None:
        self._session_factory, self._table = session_factory, table

    async def __call__(self, event: StoredEvent) -> None:  # idempotent: deleting twice is fine
        contact_id = UUID(str(event.payload["contact_id"]))
        async with SqlUnitOfWork(self._session_factory, event.tenant_id) as uow:
            await uow.session.execute(
                delete(self._table).where(self._table.c.contact_id == contact_id)
            )
            await uow.commit()


def forget_rows_in(table: Table) -> EventHandlerFactory:
    def factory(services: PlatformServices) -> EventHandler:
        return DeleteContactRows(services.session_factory, table)

    return factory
