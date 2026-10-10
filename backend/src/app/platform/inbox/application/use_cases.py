"""Staff inbox use cases (PRD §6.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.platform.inbox.application.ports import (
    ContactCard,
    InboxContacts,
    InboxMessages,
    MessageLine,
    StaffSender,
)
from app.platform.inbox.domain.handover import Handover
from app.platform.inbox.domain.repositories import HandoverRepository
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock
from app.shared.kernel.errors import NotFoundError, ValidationError
from app.shared.kernel.ids import IdGenerator, TenantId

SERVICE_WINDOW = timedelta(hours=24)


class InboxUnitOfWork(UnitOfWork, Protocol):
    @property
    def handovers(self) -> HandoverRepository: ...


@dataclass(frozen=True)
class HandoverDTO:
    reason: str
    started_at: datetime
    assigned_user_id: UUID | None

    @classmethod
    def from_domain(cls, h: Handover) -> HandoverDTO:
        return cls(h.reason, h.started_at, h.assigned_user_id)


@dataclass(frozen=True)
class ConversationSummary:
    contact: ContactCard
    last_message: MessageLine
    handover: HandoverDTO | None
    awaiting_reply: bool  # the contact wrote last


@dataclass(frozen=True)
class ConversationDetail:
    contact: ContactCard
    messages: list[MessageLine]
    handover: HandoverDTO | None
    can_send_text: bool  # inside the 24 h customer-service window (PL-5.4)
    window_closes_at: datetime | None = field(default=None)


class ListInbox:
    """Conversations, newest first; ones waiting for a person are listed first (PL-5.1)."""

    def __init__(
        self, uow: InboxUnitOfWork, messages: InboxMessages, contacts: InboxContacts
    ) -> None:
        self._uow, self._messages, self._contacts = uow, messages, contacts

    async def __call__(
        self, tenant_id: TenantId, actor: Actor, limit: int = 50
    ) -> list[ConversationSummary]:
        latest = await self._messages.latest_per_contact(tenant_id, limit)
        async with self._uow as uow:
            handovers = {h.contact_id: h for h in await uow.handovers.all_active()}
        cards = await self._contacts.cards(tenant_id, [m.contact_id for m in latest], actor)
        rows = [
            ConversationSummary(
                contact=cards[m.contact_id],
                last_message=m,
                handover=HandoverDTO.from_domain(handovers[m.contact_id])
                if m.contact_id in handovers
                else None,
                awaiting_reply=m.direction == "inbound",
            )
            for m in latest
            if m.contact_id in cards
        ]
        return sorted(
            rows, key=lambda r: (r.handover is None, -r.last_message.created_at.timestamp())
        )


class GetConversation:
    def __init__(
        self, uow: InboxUnitOfWork, messages: InboxMessages, contacts: InboxContacts, clock: Clock
    ) -> None:
        self._uow, self._messages, self._contacts, self._clock = uow, messages, contacts, clock

    async def __call__(
        self, tenant_id: TenantId, contact_id: UUID, actor: Actor
    ) -> ConversationDetail:
        cards = await self._contacts.cards(tenant_id, [contact_id], actor)
        if contact_id not in cards:
            raise NotFoundError("Conversation not found")
        contact = cards[contact_id]
        async with self._uow as uow:
            handover = await uow.handovers.active_for(contact_id)
        closes = contact.last_inbound_at + SERVICE_WINDOW if contact.last_inbound_at else None
        return ConversationDetail(
            contact=contact,
            messages=await self._messages.thread(tenant_id, contact_id, 100),
            handover=HandoverDTO.from_domain(handover) if handover else None,
            can_send_text=closes is not None and self._clock.now() < closes,
            window_closes_at=closes,
        )


class Handovers:
    """Request / take over / hand back. Used by the bot (request) and by staff."""

    def __init__(self, uow: InboxUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        self._uow, self._clock, self._ids = uow, clock, ids

    async def is_active(self, contact_id: UUID) -> bool:
        async with self._uow as uow:
            return await uow.handovers.active_for(contact_id) is not None

    async def request(self, tenant_id: TenantId, contact_id: UUID, reason: str) -> None:
        async with self._uow as uow:
            if await uow.handovers.active_for(contact_id) is None:
                await uow.handovers.add(
                    Handover.request(
                        id=self._ids.new_id(),
                        tenant_id=tenant_id,
                        contact_id=contact_id,
                        reason=reason,
                        at=self._clock.now(),
                    )
                )
                await uow.commit()

    async def take_over(self, tenant_id: TenantId, contact_id: UUID, user_id: UUID) -> HandoverDTO:
        now = self._clock.now()
        async with self._uow as uow:
            handover = await uow.handovers.active_for(contact_id)
            if handover is None:
                handover = Handover.request(
                    id=self._ids.new_id(),
                    tenant_id=tenant_id,
                    contact_id=contact_id,
                    reason="staff",
                    at=now,
                )
                handover.take_over(user_id, now)
                await uow.handovers.add(handover)
            else:
                handover.take_over(user_id, now)
                await uow.handovers.save(handover)
            await uow.commit()
        return HandoverDTO.from_domain(handover)

    async def hand_back(self, contact_id: UUID, user_id: UUID) -> None:
        async with self._uow as uow:
            handover = await uow.handovers.active_for(contact_id)
            if handover is not None:
                handover.hand_back(user_id, self._clock.now())
                await uow.handovers.save(handover)
                await uow.commit()


@dataclass(frozen=True)
class ReplyCommand:
    tenant_id: TenantId
    contact_id: UUID
    user_id: UUID
    text: str


class StaffReply:
    """Staff write to the contact over WhatsApp. Replying takes the chat over (bot goes quiet)."""

    def __init__(self, handovers: Handovers, contacts: InboxContacts, sender: StaffSender) -> None:
        self._handovers, self._contacts, self._sender = handovers, contacts, sender

    async def __call__(self, cmd: ReplyCommand) -> bool:
        text = cmd.text.strip()
        if not text or len(text) > 4096:
            raise ValidationError("A reply must be 1-4096 characters")
        cards = await self._contacts.cards(
            cmd.tenant_id, [cmd.contact_id], Actor.staff(cmd.user_id)
        )
        if cmd.contact_id not in cards:
            raise NotFoundError("Conversation not found")
        await self._handovers.take_over(cmd.tenant_id, cmd.contact_id, cmd.user_id)
        return await self._sender.send_text(cmd.tenant_id, cards[cmd.contact_id], text)
