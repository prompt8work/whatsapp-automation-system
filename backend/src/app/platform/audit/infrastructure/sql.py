"""SQL audit writer (implements the shared AuditLogger port) and reader.

The writer uses its OWN short transaction, so reads are audited even though read-only use
cases never commit. If writing the audit entry fails, the error propagates: we would rather
fail a request than serve personal data without a trace.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.audit.application.queries.list_entries import AuditFilter
from app.platform.audit.domain.entry import AuditEntry
from app.platform.audit.infrastructure.tables import audit_log
from app.shared.application.audit import AuditRecord
from app.shared.infrastructure.serialization import to_jsonable
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId


class SqlAuditLogger:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], clock: Clock, ids: IdGenerator
    ) -> None:
        self._session_factory, self._clock, self._ids = session_factory, clock, ids

    async def record(self, entry: AuditRecord) -> None:
        async with SqlUnitOfWork(self._session_factory, entry.tenant_id) as uow:
            await uow.session.execute(
                insert(audit_log).values(
                    id=self._ids.new_id(),
                    tenant_id=entry.tenant_id,
                    actor_kind=entry.actor.kind.value,
                    actor_id=entry.actor.id,
                    action=entry.action,
                    resource_type=entry.resource_type,
                    resource_id=entry.resource_id,
                    details=to_jsonable(entry.details),
                    at=self._clock.now(),
                )
            )
            await uow.commit()


class SqlAuditReadModel:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], tenant_id: TenantId
    ) -> None:
        self._session_factory, self._tenant_id = session_factory, tenant_id

    async def list(self, query: AuditFilter) -> list[AuditEntry]:
        stmt: Any = select(audit_log)
        if query.resource_type:
            stmt = stmt.where(audit_log.c.resource_type == query.resource_type)
        if query.resource_id:
            stmt = stmt.where(audit_log.c.resource_id == query.resource_id)
        if query.actor_id:
            stmt = stmt.where(audit_log.c.actor_id == query.actor_id)
        stmt = stmt.order_by(audit_log.c.at.desc()).limit(max(1, min(query.limit, 500)))
        async with SqlUnitOfWork(self._session_factory, self._tenant_id) as uow:
            rows = (await uow.session.execute(stmt)).mappings().all()
        return [
            AuditEntry(
                id=r["id"],
                actor_kind=r["actor_kind"],
                actor_id=r["actor_id"],
                action=r["action"],
                resource_type=r["resource_type"],
                resource_id=r["resource_id"],
                details=r["details"],
                at=r["at"],
            )
            for r in rows
        ]
