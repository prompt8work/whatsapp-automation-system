"""SQL implementation of the shared JobScheduler port."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.jobs.domain.job import ScheduledJob
from app.platform.jobs.infrastructure.unit_of_work import SqlJobsUnitOfWork
from app.shared.application.jobs import ScheduleJob
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator


class SqlJobScheduler:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], clock: Clock, ids: IdGenerator
    ) -> None:
        self._uow = SqlJobsUnitOfWork(session_factory)
        self._clock, self._ids = clock, ids

    async def schedule(self, job: ScheduleJob) -> None:
        async with self._uow as uow:
            await uow.jobs.add(
                ScheduledJob(
                    id=self._ids.new_id(),
                    job_type=job.job_type,
                    tenant_id=job.tenant_id,
                    run_at=job.run_at,
                    idempotency_key=job.idempotency_key,
                    payload=dict(job.payload),
                    max_attempts=job.max_attempts,
                    created_at=self._clock.now(),
                )
            )
            await uow.commit()

    async def cancel(self, idempotency_key: str) -> None:
        async with self._uow as uow:
            await uow.jobs.cancel(idempotency_key, self._clock.now())
            await uow.commit()
