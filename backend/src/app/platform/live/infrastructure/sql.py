from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.infrastructure.tables import live_changes
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork
from app.shared.kernel.ids import TenantId


class SqlLiveVersions:
    """One short transaction per read, so it works behind a transaction-mode pooler."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __call__(self, tenant_id: TenantId) -> dict[str, int]:
        async with SqlUnitOfWork(self._session_factory, tenant_id) as uow:
            rows = await uow.session.execute(select(live_changes.c.topic, live_changes.c.version))
            return {r.topic: r.version for r in rows}
