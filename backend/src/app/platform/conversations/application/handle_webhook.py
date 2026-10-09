"""Everything one Meta webhook call delivered (ARCHITECTURE §7.1).

Per message:  tenant -> contact -> store (dedupe) -> safety-net job -> pipeline -> processed.
The safety-net job (`conversations.process_inbound`, ~2 min later) is cancelled once the
message is processed. If this function crashes or times out midway, the job processes the
message later, so no message is ever lost - and none is processed twice.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from app.platform.conversations.application.ports import ContactGateway, InboundLog, TenantResolver
from app.platform.messaging.contracts import InboundMessage, WebhookBatch
from app.platform.tenancy.contracts import TenantRoute
from app.shared.application.conversation import ContactInfo
from app.shared.application.jobs import JobContext, JobScheduler, ScheduleJob
from app.shared.kernel.clock import Clock

log = logging.getLogger(__name__)
PROCESS_JOB = "conversations.process_inbound"
SAFETY_DELAY = timedelta(minutes=2)

ProcessMessage = Callable[[TenantRoute, ContactInfo, InboundMessage], Awaitable[None]]


@dataclass
class WebhookReport:
    processed: int = 0
    duplicates: int = 0
    unknown_number: int = 0
    failed: int = 0
    statuses: int = 0


def _safety_key(message_id: UUID) -> str:
    return f"{PROCESS_JOB}:{message_id}"


class HandleWebhook:
    def __init__(
        self,
        tenants: TenantResolver,
        contacts: ContactGateway,
        inbound: InboundLog,
        process: ProcessMessage,
        jobs: JobScheduler,
        clock: Clock,
    ) -> None:
        self._tenants, self._contacts, self._inbound = tenants, contacts, inbound
        self._process, self._jobs, self._clock = process, jobs, clock

    async def __call__(self, batch: WebhookBatch) -> WebhookReport:
        report = WebhookReport()
        for update in batch.statuses:
            route = await self._tenants.resolve(update.phone_number_id)
            if route is not None:
                await self._inbound.record_status(route.tenant_id, update)
                report.statuses += 1

        for message in batch.messages:
            route = await self._tenants.resolve(message.phone_number_id)
            if route is None:
                report.unknown_number += 1
                continue
            contact = await self._contacts.resolve(
                route.tenant_id, message.wa_id, message.profile_name
            )
            message_id = await self._inbound.record(route.tenant_id, contact.id, message)
            if message_id is None:
                report.duplicates += 1
                continue
            await self._jobs.schedule(
                ScheduleJob(
                    PROCESS_JOB,
                    self._clock.now() + SAFETY_DELAY,
                    _safety_key(message_id),
                    tenant_id=route.tenant_id,
                    payload={"message_id": str(message_id)},
                )
            )
            try:
                await self._process(route, contact, message)
                await self._inbound.mark_processed(route.tenant_id, message_id)
                await self._jobs.cancel(_safety_key(message_id))
                report.processed += 1
            except Exception:
                log.exception("inbound.processing_failed", extra={"message_id": str(message_id)})
                report.failed += 1  # the safety-net job will retry
        return report


class ProcessInboundJob:
    """Safety net: process a stored message that the webhook call did not finish."""

    def __init__(
        self,
        tenants: TenantResolver,
        contacts: ContactGateway,
        inbound: InboundLog,
        process: ProcessMessage,
    ) -> None:
        self._tenants, self._contacts = tenants, contacts
        self._inbound, self._process = inbound, process

    async def __call__(self, ctx: JobContext) -> None:
        assert ctx.tenant_id is not None
        message_id = UUID(ctx.payload["message_id"])
        message, processed = await self._inbound.load(ctx.tenant_id, message_id)
        if processed:
            return
        route = await self._tenants.resolve(message.phone_number_id)
        if route is None:
            return  # number disconnected meanwhile
        contact = await self._contacts.resolve(route.tenant_id, message.wa_id, message.profile_name)
        await self._process(route, contact, message)
        await self._inbound.mark_processed(route.tenant_id, message_id)
