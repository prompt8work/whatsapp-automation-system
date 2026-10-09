"""Run due scheduled jobs (called every minute by the cron tick).

Per batch: (1) lock + mark RUNNING + commit, (2) run handlers OUTSIDE any transaction,
(3) save each result in its own short transaction. Stops before the time budget is spent so
the serverless function finishes cleanly; whatever is left runs on the next tick.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta

from app.platform.jobs.application.registry import JobHandlerRegistry
from app.platform.jobs.application.unit_of_work import JobsUnitOfWork
from app.platform.jobs.domain.job import JobStatus, ScheduledJob
from app.shared.application.jobs import JobContext
from app.shared.kernel.clock import Clock

log = logging.getLogger(__name__)


class NoHandlerError(Exception):
    pass


@dataclass
class RunReport:
    succeeded: int = 0
    retrying: int = 0
    failed: int = 0
    failed_types: list[str] = field(default_factory=list)


class RunDueJobs:
    def __init__(
        self,
        uow: JobsUnitOfWork,
        handlers: JobHandlerRegistry,
        clock: Clock,
        *,
        batch_size: int = 20,
        lease: timedelta = timedelta(minutes=5),
        budget: timedelta = timedelta(seconds=40),
    ) -> None:
        self._uow, self._handlers, self._clock = uow, handlers, clock
        self._batch_size, self._lease, self._budget = batch_size, lease, budget

    async def __call__(self) -> RunReport:
        report = RunReport()
        deadline = time.monotonic() + self._budget.total_seconds()
        while time.monotonic() < deadline:
            batch = await self._claim_batch()
            if not batch:
                break
            for job in batch:
                await self._run(job, report)
        return report

    async def _claim_batch(self) -> list[ScheduledJob]:
        async with self._uow as uow:
            jobs = await uow.jobs.lock_due(self._clock.now(), self._batch_size)
            for job in jobs:
                job.start(self._clock.now(), self._lease)
                await uow.jobs.save(job)
            await uow.commit()
        return jobs

    async def _run(self, job: ScheduledJob, report: RunReport) -> None:
        handler = self._handlers.get(job.job_type)
        try:
            if handler is None:
                raise NoHandlerError(f"No handler registered for {job.job_type!r}")
            await handler(
                JobContext(job.id, job.job_type, job.tenant_id, dict(job.payload), job.attempts)
            )
        except NoHandlerError as exc:
            job.give_up(exc, self._clock.now())
            report.failed += 1
            report.failed_types.append(job.job_type)
        except Exception as exc:
            job.fail(exc, self._clock.now())
            log.warning(
                "job.failed",
                extra={"job_id": str(job.id), "job_type": job.job_type, "status": job.status},
            )
            if job.status is JobStatus.FAILED:
                report.failed += 1
                report.failed_types.append(job.job_type)
            else:
                report.retrying += 1
        else:
            job.succeed(self._clock.now())
            report.succeeded += 1
        async with self._uow as uow:
            await uow.jobs.save(job)
            await uow.commit()
