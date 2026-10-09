"""Job runner + outbox dispatcher with in-memory repositories."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta
from uuid import UUID

from app.platform.jobs.application.dispatch_outbox import DispatchOutbox
from app.platform.jobs.application.registry import EventHandlerRegistry, JobHandlerRegistry
from app.platform.jobs.application.run_due_jobs import RunDueJobs
from app.platform.jobs.domain.job import JobStatus, ScheduledJob
from app.platform.jobs.domain.outbox import MAX_DELIVERY_ATTEMPTS, OutboxDelivery
from app.platform.jobs.domain.retry import backoff
from app.shared.application.events import StoredEvent
from app.shared.application.jobs import JobContext
from app.shared.testing.fakes import FixedClock, InMemoryUnitOfWork


class InMemoryJobs:
    def __init__(self) -> None:
        self.rows: dict[UUID, ScheduledJob] = {}

    async def lock_due(self, now: datetime, limit: int) -> list[ScheduledJob]:
        due = [
            j
            for j in self.rows.values()
            if (j.status is JobStatus.PENDING and j.run_at <= now)
            or (j.status is JobStatus.RUNNING and j.locked_until and j.locked_until < now)
        ]
        return [copy.deepcopy(j) for j in sorted(due, key=lambda j: j.run_at)[:limit]]

    async def add(self, job: ScheduledJob) -> bool:
        if any(j.idempotency_key == job.idempotency_key for j in self.rows.values()):
            return False
        self.rows[job.id] = copy.deepcopy(job)
        return True

    async def save(self, job: ScheduledJob) -> None:
        self.rows[job.id] = copy.deepcopy(job)

    async def cancel(self, idempotency_key: str, now: datetime) -> None:
        pass


class InMemoryOutbox:
    def __init__(self) -> None:
        self.rows: dict[UUID, OutboxDelivery] = {}

    async def lock_due(self, now: datetime, limit: int) -> list[OutboxDelivery]:
        due = [
            d
            for d in self.rows.values()
            if d.dispatched_at is None
            and d.dead_at is None
            and (d.next_attempt_at is None or d.next_attempt_at <= now)
        ]
        return [copy.deepcopy(d) for d in due[:limit]]

    async def save(self, delivery: OutboxDelivery) -> None:
        self.rows[delivery.id] = copy.deepcopy(delivery)


class InMemoryJobsUoW(InMemoryUnitOfWork):
    def __init__(self) -> None:
        super().__init__()
        self.jobs = InMemoryJobs()
        self.outbox = InMemoryOutbox()


def job(job_type: str, run_at: datetime, n: int = 1) -> ScheduledJob:
    return ScheduledJob(
        id=UUID(int=n),
        job_type=job_type,
        tenant_id=None,
        run_at=run_at,
        idempotency_key=f"k{n}",
        created_at=run_at,
        max_attempts=2,
    )


class Flaky:
    def __init__(self, failures: int) -> None:
        self.failures, self.calls = failures, 0

    async def __call__(self, ctx: JobContext) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("temporary")


async def test_due_job_runs_once_and_future_job_waits() -> None:
    clock, uow, registry = FixedClock(), InMemoryJobsUoW(), JobHandlerRegistry()
    handler = Flaky(failures=0)
    registry.register("demo.ping", handler)
    await uow.jobs.add(job("demo.ping", clock.now(), 1))
    await uow.jobs.add(job("demo.ping", clock.now() + timedelta(hours=1), 2))
    run = RunDueJobs(uow, registry, clock)

    report = await run()
    again = await run()

    assert (report.succeeded, again.succeeded, handler.calls) == (1, 0, 1)
    assert uow.jobs.rows[UUID(int=1)].status is JobStatus.DONE
    assert uow.jobs.rows[UUID(int=2)].status is JobStatus.PENDING


async def test_failed_job_retries_with_backoff_then_gives_up() -> None:
    clock, uow, registry = FixedClock(), InMemoryJobsUoW(), JobHandlerRegistry()
    registry.register("demo.flaky", Flaky(failures=5))
    await uow.jobs.add(job("demo.flaky", clock.now()))
    run = RunDueJobs(uow, registry, clock)

    first = await run()
    stored = uow.jobs.rows[UUID(int=1)]
    assert first.retrying == 1
    assert stored.run_at == clock.now() + backoff(1)

    clock.advance(backoff(1))
    second = await run()
    assert second.failed == 1  # max_attempts=2
    assert uow.jobs.rows[UUID(int=1)].status is JobStatus.FAILED


async def test_job_without_handler_fails_immediately() -> None:
    clock, uow = FixedClock(), InMemoryJobsUoW()
    await uow.jobs.add(job("nobody.handles", clock.now()))

    report = await RunDueJobs(uow, JobHandlerRegistry(), clock)()

    assert report.failed_types == ["nobody.handles"]
    assert "No handler" in (uow.jobs.rows[UUID(int=1)].last_error or "")


async def test_crashed_running_job_is_picked_up_after_lease() -> None:
    clock, uow, registry = FixedClock(), InMemoryJobsUoW(), JobHandlerRegistry()
    registry.register("demo.ping", Flaky(failures=0))
    stuck = job("demo.ping", clock.now())
    stuck.start(clock.now(), timedelta(minutes=5))  # a previous tick died mid-run
    await uow.jobs.add(stuck)

    assert (await RunDueJobs(uow, registry, clock)()).succeeded == 0
    clock.advance(timedelta(minutes=6))
    assert (await RunDueJobs(uow, registry, clock)()).succeeded == 1


async def test_outbox_delivers_to_all_handlers_and_retries_failures() -> None:
    clock, uow, registry = FixedClock(), InMemoryJobsUoW(), EventHandlerRegistry()
    seen: list[str] = []

    async def ok(event: StoredEvent) -> None:
        seen.append(event.event_type)

    async def broken(event: StoredEvent) -> None:
        raise RuntimeError("downstream down")

    registry.register("Good", ok)
    registry.register("Bad", broken)
    for n, kind in enumerate(["Good", "Bad", "Unhandled"], start=1):
        await uow.outbox.save(
            OutboxDelivery(
                id=UUID(int=n), tenant_id=None, event_type=kind, payload={}, occurred_at=clock.now()
            )
        )

    report = await DispatchOutbox(uow, registry, clock)()

    assert (report.delivered, report.retrying) == (2, 1)  # "Unhandled" counts as delivered
    assert seen == ["Good"]
    bad = uow.outbox.rows[UUID(int=2)]
    assert bad.dispatched_at is None
    assert bad.next_attempt_at == clock.now() + backoff(1)


async def test_outbox_gives_up_after_max_attempts() -> None:
    clock, uow, registry = FixedClock(), InMemoryJobsUoW(), EventHandlerRegistry()

    async def broken(event: StoredEvent) -> None:
        raise RuntimeError("down")

    registry.register("Bad", broken)
    await uow.outbox.save(
        OutboxDelivery(
            id=UUID(int=1),
            tenant_id=None,
            event_type="Bad",
            payload={},
            occurred_at=clock.now(),
            attempts=MAX_DELIVERY_ATTEMPTS - 1,
        )
    )

    report = await DispatchOutbox(uow, registry, clock)()

    assert report.dead == 1
    assert uow.outbox.rows[UUID(int=1)].dead_at == clock.now()
