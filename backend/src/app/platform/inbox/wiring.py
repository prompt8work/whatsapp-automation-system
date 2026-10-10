"""Inbox wiring: adapters to messaging / contacts / tenancy, the HandoverDesk the conversation
pipeline uses, and the HTTP router."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter

from app.platform.contacts.contracts import GetContactsQuery
from app.platform.contacts.integration import contacts_for
from app.platform.inbox.application.ports import ContactCard, MessageLine
from app.platform.inbox.application.use_cases import (
    GetConversation,
    Handovers,
    ListInbox,
    StaffReply,
)
from app.platform.inbox.infrastructure.sql import SqlInboxUnitOfWork
from app.platform.inbox.presentation.http.routers import InboxUseCases, build_router
from app.platform.messaging.integration import MessageView, SqlMessageReadModel
from app.platform.tenancy.integration import tenancy_for
from app.shared.application.messaging import SendRequest
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import Text
from app.shared.module import PlatformServices


def _line(m: MessageView) -> MessageLine:
    return MessageLine(m.id, m.contact_id, m.direction, m.text, m.status, m.created_at, m.error)


@dataclass(frozen=True)
class MessagesAdapter:
    services: PlatformServices

    async def latest_per_contact(self, tenant_id: TenantId, limit: int) -> list[MessageLine]:
        reads = SqlMessageReadModel(self.services.session_factory, tenant_id)
        return [_line(m) for m in await reads.latest_per_contact(limit)]

    async def thread(self, tenant_id: TenantId, contact_id: UUID, limit: int) -> list[MessageLine]:
        reads = SqlMessageReadModel(self.services.session_factory, tenant_id)
        return [_line(m) for m in await reads.thread(contact_id, limit)]


@dataclass(frozen=True)
class ContactsAdapter:
    services: PlatformServices

    async def cards(
        self, tenant_id: TenantId, contact_ids: list[UUID], actor: Actor
    ) -> dict[UUID, ContactCard]:
        found = await contacts_for(self.services, tenant_id).get_many(
            GetContactsQuery(tenant_id, actor, contact_ids)
        )
        return {
            cid: ContactCard(c.id, c.phone, c.profile_name, c.last_inbound_at, c.is_opted_out)
            for cid, c in found.items()
        }


@dataclass(frozen=True)
class SenderAdapter:
    services: PlatformServices

    async def send_text(self, tenant_id: TenantId, contact: ContactCard, text: str) -> bool:
        number = await tenancy_for(self.services).sending_number(tenant_id)
        if number is None:
            return False
        receipt = await self.services.messenger.send(
            SendRequest(
                tenant_id, contact.id, contact.phone, number, Text(text), contact.last_inbound_at
            )
        )
        return receipt.sent


def handovers_for(services: PlatformServices, tenant_id: TenantId) -> Handovers:
    return Handovers(
        SqlInboxUnitOfWork(services.session_factory, tenant_id), services.clock, services.ids
    )


@dataclass(frozen=True)
class InboxHandoverDesk:
    """Implements the conversation pipeline's HandoverDesk port (R8, PL-5.3)."""

    services: PlatformServices

    async def is_active(self, tenant_id: TenantId, contact_id: UUID) -> bool:
        return await handovers_for(self.services, tenant_id).is_active(contact_id)

    async def request(self, tenant_id: TenantId, contact_id: UUID, reason: str) -> None:
        await handovers_for(self.services, tenant_id).request(tenant_id, contact_id, reason)


def inbox_use_cases(services: PlatformServices, tenant_id: TenantId) -> InboxUseCases:
    uow = SqlInboxUnitOfWork(services.session_factory, tenant_id)
    messages, contacts = MessagesAdapter(services), ContactsAdapter(services)
    handovers = handovers_for(services, tenant_id)
    return InboxUseCases(
        list_inbox=ListInbox(uow, messages, contacts),
        get_conversation=GetConversation(uow, messages, contacts, services.clock),
        handovers=handovers,
        reply=StaffReply(handovers, contacts, SenderAdapter(services)),
    )


def build_routers(services: PlatformServices) -> Sequence[APIRouter]:
    return [build_router(lambda tenant_id: inbox_use_cases(services, tenant_id))]
