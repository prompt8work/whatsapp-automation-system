"""Jobs wiring - called explicitly by bootstrap (needs the registries and the cron secret)."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.jobs.application.dispatch_outbox import DispatchOutbox
from app.platform.jobs.application.registry import EventHandlerRegistry, JobHandlerRegistry
from app.platform.jobs.application.run_due_jobs import RunDueJobs
from app.platform.jobs.infrastructure.unit_of_work import SqlJobsUnitOfWork
from app.platform.jobs.presentation.http.routers import build_router
from app.shared.kernel.clock import Clock


def build_tick_router(
    session_factory: async_sessionmaker[AsyncSession],
    clock: Clock,
    job_handlers: JobHandlerRegistry,
    event_handlers: EventHandlerRegistry,
    cron_secret: str,
) -> APIRouter:
    uow = SqlJobsUnitOfWork(session_factory)
    return build_router(
        DispatchOutbox(uow, event_handlers, clock),
        RunDueJobs(uow, job_handlers, clock),
        cron_secret,
    )
