from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.platform.jobs.domain.job import ScheduledJob
from app.platform.jobs.domain.outbox import OutboxDelivery


class JobRepository(Protocol):
    async def lock_due(self, now: datetime, limit: int) -> list[ScheduledJob]:
        """Due PENDING jobs + RUNNING jobs whose lease expired, row-locked for this
        transaction (FOR UPDATE SKIP LOCKED: parallel ticks never get the same job)."""
        ...

    async def add(self, job: ScheduledJob) -> bool:
        """False if a job with the same idempotency_key already exists."""
        ...

    async def save(self, job: ScheduledJob) -> None: ...

    async def cancel(self, idempotency_key: str, now: datetime) -> None: ...


class OutboxRepository(Protocol):
    async def lock_due(self, now: datetime, limit: int) -> list[OutboxDelivery]: ...

    async def save(self, delivery: OutboxDelivery) -> None: ...
