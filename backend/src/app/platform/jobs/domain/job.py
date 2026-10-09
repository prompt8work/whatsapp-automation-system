"""A scheduled job: "run <job_type> with <payload> at <run_at>" (ARCHITECTURE §8.5).

Lifecycle:  PENDING --start--> RUNNING --succeed--> DONE
                                       --fail-->    PENDING (retry later) | FAILED (gave up)
            PENDING --cancel--> CANCELLED
A RUNNING job whose lease expired (process crashed) is picked up again by the next tick.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from app.platform.jobs.domain.retry import backoff, short_error
from app.shared.kernel.entity import AggregateRoot
from app.shared.kernel.ids import TenantId


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(kw_only=True, eq=False)
class ScheduledJob(AggregateRoot):
    job_type: str
    tenant_id: TenantId | None
    run_at: datetime
    idempotency_key: str
    created_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    max_attempts: int = 5
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    last_error: str | None = None
    locked_until: datetime | None = None
    finished_at: datetime | None = None

    def start(self, now: datetime, lease: timedelta) -> None:
        self.status = JobStatus.RUNNING
        self.attempts += 1
        self.locked_until = now + lease

    def succeed(self, now: datetime) -> None:
        self.status = JobStatus.DONE
        self.finished_at = now
        self.locked_until = None
        self.last_error = None

    def give_up(self, error: BaseException, now: datetime) -> None:
        """Permanent failure - retrying cannot help (e.g. no handler for this job type)."""
        self.attempts = self.max_attempts
        self.fail(error, now)

    def fail(self, error: BaseException, now: datetime) -> None:
        self.last_error = short_error(error)
        self.locked_until = None
        if self.attempts >= self.max_attempts:
            self.status = JobStatus.FAILED
            self.finished_at = now
        else:
            self.status = JobStatus.PENDING
            self.run_at = now + backoff(self.attempts)
