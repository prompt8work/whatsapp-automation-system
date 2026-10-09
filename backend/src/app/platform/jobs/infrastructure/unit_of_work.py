from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.jobs.infrastructure.repositories import SqlJobRepository, SqlOutboxRepository
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork


class SqlJobsUnitOfWork(SqlUnitOfWork):
    jobs: SqlJobRepository
    outbox: SqlOutboxRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory, tenant_id=None)

    def _create_repositories(self) -> None:
        self.jobs = SqlJobRepository(self.session)
        self.outbox = SqlOutboxRepository(self.session)
