"""SendMessage / RetrySend use cases with in-memory fakes."""

from __future__ import annotations

import copy
from datetime import timedelta
from uuid import UUID

import pytest

from app.platform.messaging.application.commands.send_message import (
    RETRY_JOB,
    OutsideServiceWindowError,
    RetrySend,
    SendMessage,
)
from app.platform.messaging.application.ports import SendError
from app.platform.messaging.domain.message import Message, MessageStatus
from app.platform.messaging.infrastructure.recording import RecordingGateway
from app.shared.application.jobs import JobContext, ScheduleJob
from app.shared.application.messaging import SendRequest
from app.shared.kernel.errors import NotFoundError
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import Template, Text
from app.shared.testing.fakes import FixedClock, InMemoryUnitOfWork, SequentialIds

TENANT = TenantId(UUID(int=9))


class Messages:
    def __init__(self) -> None:
        self.rows: dict[UUID, Message] = {}

    async def get(self, message_id: UUID) -> Message:
        if message_id not in self.rows:
            raise NotFoundError()
        return copy.deepcopy(self.rows[message_id])

    async def add(self, message: Message) -> None:
        self.rows[message.id] = copy.deepcopy(message)

    async def add_inbound(self, message: Message) -> bool:
        await self.add(message)
        return True

    async def find_by_wa_id(self, wa_message_id: str) -> Message | None:
        return None

    async def save(self, message: Message) -> None:
        self.rows[message.id] = copy.deepcopy(message)


class MessagesUoW(InMemoryUnitOfWork):
    def __init__(self) -> None:
        super().__init__()
        self.messages = Messages()


class Credentials:
    def __init__(self, token: str | None = "token") -> None:
        self.token = token

    async def get(self, phone_number_id: str) -> str | None:
        return self.token

    async def put(self, phone_number_id: str, access_token: str) -> None:
        self.token = access_token


class Jobs:
    def __init__(self) -> None:
        self.scheduled: list[ScheduleJob] = []

    async def schedule(self, job: ScheduleJob) -> None:
        self.scheduled.append(job)

    async def cancel(self, idempotency_key: str) -> None:
        pass


class World:
    def __init__(self, token: str | None = "token") -> None:
        self.clock, self.uow, self.gateway = FixedClock(), MessagesUoW(), RecordingGateway()
        self.jobs, self.credentials = Jobs(), Credentials(token)
        self.send = SendMessage(
            self.uow, self.gateway, self.credentials, self.jobs, self.clock, SequentialIds()
        )

    def request(self, message: object, *, hours_since_reply: float = 0.1) -> SendRequest:
        return SendRequest(
            TENANT,
            UUID(int=1),
            "+919876543210",
            "123",
            message,  # type: ignore[arg-type]
            self.clock.now() - timedelta(hours=hours_since_reply),
        )


async def test_sends_and_logs_message() -> None:
    world = World()
    receipt = await world.send(world.request(Text("Hello")))

    assert receipt.sent
    stored = world.uow.messages.rows[receipt.message_id]
    assert stored.status is MessageStatus.SENT
    assert stored.wa_message_id == world.gateway.sent[0].wa_message_id
    assert world.gateway.sent[0].to == "919876543210"  # Meta wants digits without "+"


async def test_free_text_is_refused_outside_24h_window_but_templates_are_allowed() -> None:
    world = World()
    with pytest.raises(OutsideServiceWindowError):
        await world.send(world.request(Text("Late"), hours_since_reply=25))

    receipt = await world.send(world.request(Template("reminder"), hours_since_reply=25))
    assert receipt.sent


async def test_transient_failure_schedules_retry_which_resends_once() -> None:
    world = World()
    world.gateway.fail_next = SendError("Meta 500", transient=True)

    receipt = await world.send(world.request(Text("Hello")))

    assert not receipt.sent
    [job] = world.jobs.scheduled
    assert job.job_type == RETRY_JOB

    retry = RetrySend(
        lambda _t: world.uow, world.gateway, world.credentials, world.jobs, world.clock
    )
    ctx = JobContext(UUID(int=99), RETRY_JOB, TENANT, job.payload, attempt=1)
    await retry(ctx)
    await retry(ctx)  # running the job twice must not send twice

    assert [s.message for s in world.gateway.sent] == [Text("Hello")]
    assert world.uow.messages.rows[receipt.message_id].status is MessageStatus.SENT


async def test_permanent_failure_is_logged_without_retry() -> None:
    world = World(token=None)  # number has no access token configured

    receipt = await world.send(world.request(Text("Hello")))

    assert not receipt.sent
    assert world.jobs.scheduled == []
    assert "No access token" in (world.uow.messages.rows[receipt.message_id].error or "")
