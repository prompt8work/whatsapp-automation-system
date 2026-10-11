"""Messaging wiring. Bootstrap builds ONE gateway + credential store and passes them in."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.messaging.application.commands.inbound import (
    LoadInbound,
    MarkInboundProcessed,
    RecordInbound,
)
from app.platform.messaging.application.commands.send_message import RetrySend, SendMessage
from app.platform.messaging.application.commands.statuses import RecordDeliveryStatus
from app.platform.messaging.application.commands.templates import TemplateSettings
from app.platform.messaging.application.ports import WhatsAppGateway
from app.platform.messaging.domain.repositories import CredentialStore
from app.platform.messaging.infrastructure.unit_of_work import SqlMessagingUnitOfWork
from app.platform.messaging.presentation.http.templates import (
    build_router as build_templates_http_router,
)
from app.shared.application.jobs import JobScheduler
from app.shared.application.messaging import SendReceipt, SendRequest, TemplateSlot
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId
from app.shared.module import PlatformServices


@dataclass(frozen=True)
class TenantMessenger:
    """Implements the shared Messenger port for every tenant."""

    session_factory: async_sessionmaker[AsyncSession]
    gateway: WhatsAppGateway
    credentials: CredentialStore
    jobs: JobScheduler
    clock: Clock
    ids: IdGenerator

    async def send(self, request: SendRequest) -> SendReceipt:
        uow = SqlMessagingUnitOfWork(self.session_factory, request.tenant_id)
        send = SendMessage(uow, self.gateway, self.credentials, self.jobs, self.clock, self.ids)
        return await send(request)

    def retry_handler(self) -> RetrySend:
        return RetrySend(
            lambda tenant_id: SqlMessagingUnitOfWork(self.session_factory, tenant_id),
            self.gateway,
            self.credentials,
            self.jobs,
            self.clock,
        )


@dataclass(frozen=True)
class InboundUseCases:
    record_inbound: RecordInbound
    mark_processed: MarkInboundProcessed
    load: LoadInbound
    record_status: RecordDeliveryStatus


def inbound_use_cases(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: TenantId,
    clock: Clock,
    ids: IdGenerator,
) -> InboundUseCases:
    uow = SqlMessagingUnitOfWork(session_factory, tenant_id)
    return InboundUseCases(
        record_inbound=RecordInbound(uow, clock, ids),
        mark_processed=MarkInboundProcessed(uow),
        load=LoadInbound(uow),
        record_status=RecordDeliveryStatus(uow),
    )


def build_templates_router(services: PlatformServices, slots: Sequence[TemplateSlot]) -> APIRouter:
    """Needs every module's slots, so app/main.py mounts it explicitly."""
    return build_templates_http_router(
        lambda tenant_id: TemplateSettings(
            SqlMessagingUnitOfWork(services.session_factory, tenant_id), slots, services.audit
        )
    )
