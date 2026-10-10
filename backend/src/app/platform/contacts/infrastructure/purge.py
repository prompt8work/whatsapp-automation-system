"""Retention RT-4: a contact nobody needs any more is deleted (PRD §7.10).

"Nobody needs it" = no conversation for DORMANT_AFTER and no row anywhere points at it with a
foreign key. That is how a module keeps a contact alive without contacts knowing the module:
patients.contact_id -> contacts.id means "while a patient exists, keep the number". Rows
WITHOUT such a key (message log, conversation session, handovers) are deleted afterwards by
their own modules' ContactForgotten handlers.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Column, and_, delete, exists, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.contacts.domain.events import ContactForgotten
from app.platform.contacts.infrastructure.tables import contacts
from app.shared.application.retention import PurgeResult, PurgeTarget
from app.shared.infrastructure.tables import metadata
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import TenantId

DORMANT_AFTER = timedelta(days=60)
RULE = "RT-4"


def _holders() -> Iterator[Column[Any]]:
    """Every column (of every loaded table) with a foreign key to contacts.id."""
    for table in metadata.tables.values():
        for fk in table.foreign_keys:
            if fk.column.table is contacts and fk.column.name == "id":
                yield fk.parent


def _purgeable(until: datetime) -> Any:
    last_seen = func.coalesce(contacts.c.last_inbound_at, contacts.c.first_seen_at)
    free = [not_(exists().where(col == contacts.c.id)) for col in _holders()]
    return and_(last_seen + DORMANT_AFTER <= until, *free)


class ContactPurger:
    key = "contacts.dormant"

    def __init__(self, purge_sessions: async_sessionmaker[AsyncSession], clock: Clock) -> None:
        self._sessions, self._clock = purge_sessions, clock

    async def due(self, tenant_id: TenantId, until: datetime) -> list[PurgeTarget]:
        last_seen = func.coalesce(contacts.c.last_inbound_at, contacts.c.first_seen_at)
        stmt = select(contacts.c.id, last_seen.label("last_seen")).where(_purgeable(until))
        async with SqlUnitOfWork(self._sessions, tenant_id) as uow:
            rows = (await uow.session.execute(stmt)).all()
        # No label: an unused contact has no name worth showing (and the number is personal).
        return [PurgeTarget("contact", r.id, RULE, r.last_seen + DORMANT_AFTER) for r in rows]

    async def purge(self, tenant_id: TenantId, target: PurgeTarget) -> PurgeResult:
        contact_id: UUID = target.subject_id
        now = self._clock.now()
        async with SqlUnitOfWork(self._sessions, tenant_id) as uow:
            gone = await uow.session.execute(
                delete(contacts)
                .where(contacts.c.id == contact_id, _purgeable(now))
                .returning(contacts.c.id)
            )
            if gone.first() is None:  # talked again / got a patient since `due`
                return PurgeResult()
            uow.publish(ContactForgotten(occurred_at=now, contact_id=contact_id))
            await uow.commit()
        return PurgeResult({"contacts": 1})
