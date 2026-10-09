"""HandleWebhook: routing, dedupe and the safety net, with fakes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.platform.conversations.application.handle_webhook import (
    PROCESS_JOB,
    HandleWebhook,
    ProcessInboundJob,
)
from app.platform.conversations.testing import FakeContacts
from app.platform.messaging.contracts import (
    DeliveryStatus,
    InboundKind,
    InboundMessage,
    StatusUpdate,
    WebhookBatch,
)
from app.platform.tenancy.contracts import TenantRoute
from app.shared.application.conversation import ContactInfo
from app.shared.application.jobs import JobContext, ScheduleJob
from app.shared.kernel.ids import TenantId
from app.shared.testing.fakes import FixedClock

TENANT = TenantId(UUID(int=1))
KNOWN = "111"


class Tenants:
    async def resolve(self, phone_number_id: str) -> TenantRoute | None:
        return (
            TenantRoute(TENANT, uuid4(), "Asia/Kolkata", frozenset())
            if phone_number_id == KNOWN
            else None
        )


class Inbound:
    def __init__(self) -> None:
        self.stored: dict[str, UUID] = {}
        self.messages: dict[UUID, InboundMessage] = {}
        self.processed: set[UUID] = set()
        self.statuses: list[StatusUpdate] = []

    async def record(
        self, tenant_id: TenantId, contact_id: UUID, message: InboundMessage
    ) -> UUID | None:
        if message.wa_message_id in self.stored:
            return None
        self.stored[message.wa_message_id] = uuid4()
        self.messages[self.stored[message.wa_message_id]] = message
        return self.stored[message.wa_message_id]

    async def mark_processed(self, tenant_id: TenantId, message_id: UUID) -> None:
        self.processed.add(message_id)

    async def load(self, tenant_id: TenantId, message_id: UUID) -> tuple[InboundMessage, bool]:
        return self.messages[message_id], message_id in self.processed

    async def record_status(self, tenant_id: TenantId, update: StatusUpdate) -> None:
        self.statuses.append(update)


class Jobs:
    def __init__(self) -> None:
        self.pending: dict[str, ScheduleJob] = {}

    async def schedule(self, job: ScheduleJob) -> None:
        self.pending.setdefault(job.idempotency_key, job)

    async def cancel(self, idempotency_key: str) -> None:
        self.pending.pop(idempotency_key, None)


class Pipeline:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail = False

    async def __call__(
        self, route: TenantRoute, contact: ContactInfo, message: InboundMessage
    ) -> None:
        if self.fail:
            raise RuntimeError("crash mid-processing")
        self.calls.append(message.text)


def inbound(text: str, *, wamid: str = "wamid.1", number: str = KNOWN) -> InboundMessage:
    return InboundMessage(
        number, wamid, "919876543210", None, datetime.now(UTC), InboundKind.TEXT, text
    )


def build() -> tuple[HandleWebhook, Inbound, Jobs, Pipeline]:
    store, jobs, pipeline = Inbound(), Jobs(), Pipeline()
    handle = HandleWebhook(Tenants(), FakeContacts(), store, pipeline, jobs, FixedClock())
    return handle, store, jobs, pipeline


async def test_message_is_processed_once_even_if_meta_retries() -> None:
    handle, store, jobs, pipeline = build()
    batch = WebhookBatch(messages=[inbound("hi")], statuses=[])

    first = await handle(batch)
    second = await handle(batch)  # Meta re-delivers the same webhook

    assert (first.processed, second.duplicates) == (1, 1)
    assert pipeline.calls == ["hi"]
    assert jobs.pending == {}  # safety net cancelled after success
    assert len(store.processed) == 1


async def test_messages_to_unknown_numbers_are_ignored() -> None:
    handle, _, _, pipeline = build()
    report = await handle(WebhookBatch(messages=[inbound("hi", number="999")], statuses=[]))
    assert report.unknown_number == 1
    assert pipeline.calls == []


async def test_crash_leaves_safety_job_which_processes_the_message_later() -> None:
    handle, store, jobs, pipeline = build()
    pipeline.fail = True

    report = await handle(WebhookBatch(messages=[inbound("hi")], statuses=[]))

    assert report.failed == 1
    [job] = jobs.pending.values()
    assert job.job_type == PROCESS_JOB

    pipeline.fail = False
    process = ProcessInboundJob(Tenants(), FakeContacts(), store, pipeline)
    ctx = JobContext(uuid4(), PROCESS_JOB, TENANT, job.payload, attempt=1)
    await process(ctx)
    await process(ctx)  # idempotent: already processed

    assert pipeline.calls == ["hi"]


async def test_delivery_statuses_are_recorded() -> None:
    handle, store, _, _ = build()
    update = StatusUpdate(KNOWN, "wamid.out", DeliveryStatus.READ, datetime.now(UTC))
    report = await handle(WebhookBatch(messages=[], statuses=[update]))
    assert report.statuses == 1
    assert store.statuses == [update]
