"""Scheduled jobs port (ARCHITECTURE §8.5).

Schedule:   await scheduler.schedule(ScheduleJob("appointments.send_reminder", run_at, ...))
Handle:     a module registers {"appointments.send_reminder": factory} in its ModuleDefinition;
            the factory receives PlatformServices and returns a JobHandler.

Handlers MUST be idempotent: a job can run more than once (crash after work, before "done").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.shared.kernel.ids import TenantId


@dataclass(frozen=True)
class ScheduleJob:
    job_type: str
    run_at: datetime
    idempotency_key: str  # same key twice = scheduled once (e.g. "reminder:24h:<appointment_id>")
    tenant_id: TenantId | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    max_attempts: int = 5


class JobScheduler(Protocol):
    async def schedule(self, job: ScheduleJob) -> None: ...

    async def cancel(self, idempotency_key: str) -> None:
        """Cancel a pending job (e.g. reminders of a rescheduled appointment). No-op if absent."""
        ...


@dataclass(frozen=True)
class JobContext:
    job_id: UUID
    job_type: str
    tenant_id: TenantId | None
    payload: dict[str, Any]
    attempt: int


class JobHandler(Protocol):
    async def __call__(self, ctx: JobContext) -> None: ...
