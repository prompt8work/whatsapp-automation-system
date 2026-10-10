"""Once-a-day jobs (e.g. the retention purge). Each cron tick makes sure today's occurrence is
scheduled; the idempotency key "<job_type>:<date>" makes repeated ticks no-ops."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, time

from app.shared.application.jobs import JobScheduler, ScheduleJob
from app.shared.kernel.clock import Clock


class EnsureDailyJobs:
    def __init__(self, scheduler: JobScheduler, clock: Clock, daily: Mapping[str, int]) -> None:
        self._scheduler, self._clock, self._daily = scheduler, clock, daily

    async def __call__(self) -> None:
        today = self._clock.now().astimezone(UTC).date()
        for job_type, hour in self._daily.items():
            await self._scheduler.schedule(
                ScheduleJob(
                    job_type,
                    datetime.combine(today, time(hour), UTC),
                    f"{job_type}:{today.isoformat()}",
                    max_attempts=3,
                )
            )
