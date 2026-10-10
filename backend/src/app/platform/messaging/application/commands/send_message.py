"""Send one message to a contact and log it (PRD PL-4.1 - PL-4.3).

1. Enforce the 24-hour customer-service window: free-form messages only within 24 h of
   the contact's last message; outside it, only approved Templates (PL-4.2).
2. Log the message as QUEUED and commit (so it is visible even if sending crashes).
3. Call the gateway; mark SENT or FAILED.
4. Transient failure (timeout, 5xx, rate limit) -> schedule `messaging.retry_send`; the job
   runner retries with back-off.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from uuid import UUID

from app.platform.messaging.application.ports import SendError, WhatsAppGateway
from app.platform.messaging.application.unit_of_work import MessagingUnitOfWork
from app.platform.messaging.domain.message import Message, MessageStatus
from app.platform.messaging.domain.repositories import CredentialStore
from app.shared.application.jobs import JobContext, JobScheduler, ScheduleJob
from app.shared.application.messaging import (
    OutsideServiceWindowError,
    SendReceipt,
    SendRequest,
)
from app.shared.kernel.clock import Clock
from app.shared.kernel.errors import DomainError
from app.shared.kernel.ids import IdGenerator, TenantId
from app.shared.kernel.messages import OutboundMessage, Template, from_content, to_content

CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)
RETRY_JOB = "messaging.retry_send"


class MissingCredentialsError(DomainError):
    code = "messaging.no_credentials"


class _Delivery:
    """Shared by SendMessage and the retry job: credentials -> gateway -> log result."""

    def __init__(
        self,
        uow: MessagingUnitOfWork,
        gateway: WhatsAppGateway,
        credentials: CredentialStore,
        jobs: JobScheduler,
        clock: Clock,
    ) -> None:
        self._uow, self._gateway, self._credentials = uow, gateway, credentials
        self._jobs, self._clock = jobs, clock

    async def deliver(
        self, message: Message, outbound: OutboundMessage, *, schedule_retry: bool
    ) -> None:
        token = await self._credentials.get(message.phone_number_id)
        try:
            if token is None:
                raise SendError("No access token for this number", transient=False, code="no_token")
            wa_id = await self._gateway.send(
                phone_number_id=message.phone_number_id,
                access_token=token,
                to=message.meta["to"].lstrip("+"),
                message=outbound,
            )
        except SendError as exc:
            message.mark_send_failed(str(exc))
            await self._save(message)
            if exc.transient and schedule_retry:
                await self._jobs.schedule(
                    ScheduleJob(
                        RETRY_JOB,
                        self._clock.now() + timedelta(minutes=1),
                        f"{RETRY_JOB}:{message.id}",
                        tenant_id=message.tenant_id,
                        payload={"message_id": str(message.id)},
                    )
                )
            elif exc.transient:
                raise  # inside the retry job: let the runner back off and retry
            return
        message.mark_sent(wa_id)
        await self._save(message)

    async def _save(self, message: Message) -> None:
        async with self._uow as uow:
            await uow.messages.save(message)
            await uow.commit()


class SendMessage:
    def __init__(
        self,
        uow: MessagingUnitOfWork,
        gateway: WhatsAppGateway,
        credentials: CredentialStore,
        jobs: JobScheduler,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow, self._clock, self._ids = uow, clock, ids
        self._delivery = _Delivery(uow, gateway, credentials, jobs, clock)

    async def __call__(self, cmd: SendRequest) -> SendReceipt:
        now = self._clock.now()
        in_window = (
            cmd.last_inbound_at is not None and now - cmd.last_inbound_at < CUSTOMER_SERVICE_WINDOW
        )
        if not in_window and not isinstance(cmd.message, Template):
            raise OutsideServiceWindowError("Only templates can be sent 24 h after the last reply")

        message = Message.outbound(
            id=self._ids.new_id(),
            tenant_id=cmd.tenant_id,
            contact_id=cmd.contact_id,
            phone_number_id=cmd.phone_number_id,
            content=to_content(cmd.message),
            at=now,
        )
        message.meta["to"] = cmd.to
        async with self._uow as uow:
            await uow.messages.add(message)
            await uow.commit()

        await self._delivery.deliver(message, cmd.message, schedule_retry=True)
        return SendReceipt(message.id, sent=message.status is MessageStatus.SENT)


class RetrySend:
    """Job handler for `messaging.retry_send`. Idempotent: skips already-sent messages."""

    def __init__(
        self,
        uow_for: Callable[[TenantId], MessagingUnitOfWork],
        gateway: WhatsAppGateway,
        credentials: CredentialStore,
        jobs: JobScheduler,
        clock: Clock,
    ) -> None:
        self._uow_for, self._gateway, self._credentials = uow_for, gateway, credentials
        self._jobs, self._clock = jobs, clock

    async def __call__(self, ctx: JobContext) -> None:
        assert ctx.tenant_id is not None
        uow = self._uow_for(ctx.tenant_id)
        async with uow:
            message = await uow.messages.get(UUID(ctx.payload["message_id"]))
        if message.status is not MessageStatus.FAILED:
            return
        delivery = _Delivery(uow, self._gateway, self._credentials, self._jobs, self._clock)
        await delivery.deliver(message, from_content(message.content), schedule_retry=False)
