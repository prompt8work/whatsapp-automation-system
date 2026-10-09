"""Log incoming messages. Storing first, with a unique wa_message_id, is what makes webhook
retries harmless: the second delivery is recognised and skipped (PRD AC-11)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.platform.messaging.application.unit_of_work import MessagingUnitOfWork
from app.platform.messaging.domain.inbound import InboundKind, InboundMessage
from app.platform.messaging.domain.message import Message, MessageStatus
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId


@dataclass(frozen=True)
class RecordInboundCommand:
    tenant_id: TenantId
    contact_id: UUID
    message: InboundMessage


class RecordInbound:
    def __init__(self, uow: MessagingUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        self._uow, self._clock, self._ids = uow, clock, ids

    async def __call__(self, cmd: RecordInboundCommand) -> UUID | None:
        """Returns the new message id, or None if this message was already received."""
        m = cmd.message
        message = Message.inbound(
            id=self._ids.new_id(),
            tenant_id=cmd.tenant_id,
            contact_id=cmd.contact_id,
            phone_number_id=m.phone_number_id,
            wa_message_id=m.wa_message_id,
            content={"kind": m.kind.value, "text": m.text, "choice_id": m.choice_id},
            at=self._clock.now(),
        )
        message.meta.update(
            wa_id=m.wa_id, profile_name=m.profile_name, sent_at=m.sent_at.isoformat()
        )
        async with self._uow as uow:
            is_new = await uow.messages.add_inbound(message)
            await uow.commit()
        return message.id if is_new else None


class MarkInboundProcessed:
    def __init__(self, uow: MessagingUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, message_id: UUID) -> None:
        async with self._uow as uow:
            message = await uow.messages.get(message_id)
            message.mark_processed()
            await uow.messages.save(message)
            await uow.commit()


class LoadInbound:
    """Rebuild a stored inbound message (for the conversation safety-net job)."""

    def __init__(self, uow: MessagingUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, message_id: UUID) -> tuple[InboundMessage, bool]:
        async with self._uow as uow:
            stored = await uow.messages.get(message_id)
        assert stored.wa_message_id is not None
        message = InboundMessage(
            phone_number_id=stored.phone_number_id,
            wa_message_id=stored.wa_message_id,
            wa_id=stored.meta["wa_id"],
            profile_name=stored.meta.get("profile_name"),
            sent_at=datetime.fromisoformat(stored.meta["sent_at"]),
            kind=InboundKind(stored.content["kind"]),
            text=stored.content["text"],
            choice_id=stored.content.get("choice_id"),
        )
        return message, stored.status is MessageStatus.PROCESSED
