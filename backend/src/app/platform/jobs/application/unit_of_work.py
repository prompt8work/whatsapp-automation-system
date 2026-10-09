from __future__ import annotations

from typing import Protocol

from app.platform.jobs.domain.repositories import JobRepository, OutboxRepository
from app.shared.application.unit_of_work import UnitOfWork


class JobsUnitOfWork(UnitOfWork, Protocol):
    """Platform-level (no tenant): the runner works across all tenants. Handlers open their
    own tenant-scoped Units of Work using the job's/event's tenant_id."""

    @property
    def jobs(self) -> JobRepository: ...

    @property
    def outbox(self) -> OutboxRepository: ...
