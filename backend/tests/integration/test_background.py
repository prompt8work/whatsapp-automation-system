"""The cron tick against a real database: outbox delivery + scheduled jobs."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.shared.application.events import StoredEvent
from app.shared.application.jobs import JobContext, ScheduleJob
from tests.integration.conftest import CRON_SECRET, Api, unique

pytestmark = pytest.mark.db
TICK = "/internal/jobs/tick"
CRON = {"Authorization": f"Bearer {CRON_SECRET}"}


async def test_tick_requires_cron_secret(api: Api) -> None:
    assert (await api.client.get(TICK)).status_code == 401
    assert (await api.client.get(TICK, headers={"Authorization": "Bearer nope"})).status_code == 401


async def test_scheduled_job_runs_exactly_once(api: Api) -> None:
    calls: list[JobContext] = []

    async def handler(ctx: JobContext) -> None:
        calls.append(ctx)

    job_type = unique("test.ping")
    api.container.job_handlers.register(job_type, handler)
    key = unique("key")
    job = ScheduleJob(
        job_type, api.container.clock.now() - timedelta(seconds=1), key, payload={"n": 1}
    )
    await api.container.jobs.schedule(job)
    await api.container.jobs.schedule(job)  # same idempotency key -> ignored

    first = await api.client.get(TICK, headers=CRON)
    second = await api.client.post(TICK, headers=CRON)

    assert first.status_code == 200, first.text
    assert [c.payload for c in calls if c.job_type == job_type] == [{"n": 1}]
    assert second.status_code == 200


async def test_cancelled_job_never_runs(api: Api) -> None:
    calls: list[JobContext] = []

    async def handler(ctx: JobContext) -> None:
        calls.append(ctx)

    job_type = unique("test.cancel")
    api.container.job_handlers.register(job_type, handler)
    key = unique("key")
    await api.container.jobs.schedule(
        ScheduleJob(job_type, api.container.clock.now() - timedelta(seconds=1), key)
    )
    await api.container.jobs.cancel(key)

    await api.client.get(TICK, headers=CRON)

    assert calls == []


async def test_domain_events_reach_handlers_through_the_outbox(api: Api) -> None:
    received: list[StoredEvent] = []

    async def on_tenant_created(event: StoredEvent) -> None:
        received.append(event)

    api.container.event_handlers.register("TenantCreated", on_tenant_created)
    root = await api.login(await api.create_super_admin())
    tenant_id = await api.create_tenant(root)

    response = await api.client.get(TICK, headers=CRON)

    assert response.status_code == 200
    assert tenant_id in {e.payload["tenant_id"] for e in received}
