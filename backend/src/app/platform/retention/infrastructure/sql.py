from __future__ import annotations

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.retention.domain.record import DeletionRecord
from app.platform.retention.infrastructure.tables import deletion_records
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork
from app.shared.kernel.ids import TenantId


class SqlDeletionRecords:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, record: DeletionRecord) -> None:
        async with SqlUnitOfWork(self._session_factory, record.tenant_id) as uow:
            await uow.session.execute(
                insert(deletion_records).values(
                    id=record.id,
                    tenant_id=record.tenant_id,
                    purger=record.purger,
                    subject_type=record.subject_type,
                    subject_id=record.subject_id,
                    rule=record.rule,
                    counts=record.counts,
                    at=record.at,
                )
            )
            await uow.commit()

    async def list(self, tenant_id: TenantId, limit: int) -> list[DeletionRecord]:
        stmt = select(deletion_records).order_by(deletion_records.c.at.desc()).limit(limit)
        async with SqlUnitOfWork(self._session_factory, tenant_id) as uow:
            rows = (await uow.session.execute(stmt)).mappings().all()
        return [
            DeletionRecord(
                id=r["id"],
                tenant_id=r["tenant_id"],
                purger=r["purger"],
                subject_type=r["subject_type"],
                subject_id=r["subject_id"],
                rule=r["rule"],
                counts=r["counts"],
                at=r["at"],
            )
            for r in rows
        ]
