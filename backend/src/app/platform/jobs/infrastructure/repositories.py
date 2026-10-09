from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import RowMapping, and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.jobs.domain.job import JobStatus, ScheduledJob
from app.platform.jobs.domain.outbox import OutboxDelivery
from app.platform.jobs.infrastructure.tables import scheduled_jobs
from app.shared.infrastructure.tables import outbox
from app.shared.kernel.ids import TenantId


def _job(row: RowMapping) -> ScheduledJob:
    return ScheduledJob(
        id=row["id"],
        job_type=row["job_type"],
        tenant_id=TenantId(row["tenant_id"]) if row["tenant_id"] else None,
        run_at=row["run_at"],
        idempotency_key=row["idempotency_key"],
        payload=dict(row["payload"]),
        max_attempts=row["max_attempts"],
        status=JobStatus(row["status"]),
        attempts=row["attempts"],
        last_error=row["last_error"],
        locked_until=row["locked_until"],
        created_at=row["created_at"],
        finished_at=row["finished_at"],
    )


def _job_row(job: ScheduledJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "tenant_id": job.tenant_id,
        "run_at": job.run_at,
        "idempotency_key": job.idempotency_key,
        "payload": job.payload,
        "max_attempts": job.max_attempts,
        "status": job.status.value,
        "attempts": job.attempts,
        "last_error": job.last_error,
        "locked_until": job.locked_until,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }


class SqlJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_due(self, now: datetime, limit: int) -> list[ScheduledJob]:
        c = scheduled_jobs.c
        stmt = (
            select(scheduled_jobs)
            .where(
                or_(
                    and_(c.status == JobStatus.PENDING.value, c.run_at <= now),
                    and_(c.status == JobStatus.RUNNING.value, c.locked_until < now),
                )
            )
            .order_by(c.run_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return [_job(r) for r in (await self._session.execute(stmt)).mappings()]

    async def add(self, job: ScheduledJob) -> bool:
        result = await self._session.execute(
            insert(scheduled_jobs)
            .values(_job_row(job))
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(scheduled_jobs.c.id)
        )
        return result.scalar_one_or_none() is not None

    async def save(self, job: ScheduledJob) -> None:
        await self._session.execute(
            update(scheduled_jobs).where(scheduled_jobs.c.id == job.id).values(_job_row(job))
        )

    async def cancel(self, idempotency_key: str, now: datetime) -> None:
        await self._session.execute(
            update(scheduled_jobs)
            .where(
                scheduled_jobs.c.idempotency_key == idempotency_key,
                scheduled_jobs.c.status == JobStatus.PENDING.value,
            )
            .values(status=JobStatus.CANCELLED.value, finished_at=now)
        )


class SqlOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_due(self, now: datetime, limit: int) -> list[OutboxDelivery]:
        c = outbox.c
        stmt = (
            select(outbox)
            .where(
                c.dispatched_at.is_(None),
                c.dead_at.is_(None),
                or_(c.next_attempt_at.is_(None), c.next_attempt_at <= now),
            )
            .order_by(c.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return [
            OutboxDelivery(
                id=r["id"],
                tenant_id=TenantId(r["tenant_id"]) if r["tenant_id"] else None,
                event_type=r["event_type"],
                payload=dict(r["payload"]),
                occurred_at=r["occurred_at"],
                attempts=r["attempts"],
                next_attempt_at=r["next_attempt_at"],
                last_error=r["last_error"],
                dispatched_at=r["dispatched_at"],
                dead_at=r["dead_at"],
            )
            for r in (await self._session.execute(stmt)).mappings()
        ]

    async def save(self, delivery: OutboxDelivery) -> None:
        await self._session.execute(
            update(outbox)
            .where(outbox.c.id == delivery.id)
            .values(
                attempts=delivery.attempts,
                next_attempt_at=delivery.next_attempt_at,
                last_error=delivery.last_error,
                dispatched_at=delivery.dispatched_at,
                dead_at=delivery.dead_at,
            )
        )
