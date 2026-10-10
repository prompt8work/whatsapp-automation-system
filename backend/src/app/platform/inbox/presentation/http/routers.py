"""/inbox - mounted under /api. Staff with `inbox.read` see conversations; `inbox.reply` can take
over, hand back and reply."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from app.platform.inbox.application.ports import ContactCard, MessageLine
from app.platform.inbox.application.use_cases import (
    ConversationDetail,
    ConversationSummary,
    GetConversation,
    HandoverDTO,
    Handovers,
    ListInbox,
    ReplyCommand,
    StaffReply,
)
from app.shared.kernel.ids import TenantId
from app.shared.presentation.request_context import RequestContext, require

CanRead = Annotated[RequestContext, Depends(require("inbox.read"))]
CanReply = Annotated[RequestContext, Depends(require("inbox.reply"))]


class ContactSchema(BaseModel):
    id: UUID
    phone: str
    profile_name: str | None
    last_inbound_at: datetime | None
    is_opted_out: bool

    @classmethod
    def of(cls, c: ContactCard) -> ContactSchema:
        return cls(**vars(c))


class MessageSchema(BaseModel):
    id: UUID
    direction: str
    text: str
    status: str
    created_at: datetime
    error: str | None

    @classmethod
    def of(cls, m: MessageLine) -> MessageSchema:
        return cls(
            id=m.id,
            direction=m.direction,
            text=m.text,
            status=m.status,
            created_at=m.created_at,
            error=m.error,
        )


class HandoverSchema(BaseModel):
    reason: str
    started_at: datetime
    assigned_user_id: UUID | None

    @classmethod
    def of(cls, h: HandoverDTO | None) -> HandoverSchema | None:
        return (
            cls(reason=h.reason, started_at=h.started_at, assigned_user_id=h.assigned_user_id)
            if h
            else None
        )


class ConversationSummarySchema(BaseModel):
    contact: ContactSchema
    last_message: MessageSchema
    handover: HandoverSchema | None
    awaiting_reply: bool

    @classmethod
    def of(cls, s: ConversationSummary) -> ConversationSummarySchema:
        return cls(
            contact=ContactSchema.of(s.contact),
            last_message=MessageSchema.of(s.last_message),
            handover=HandoverSchema.of(s.handover),
            awaiting_reply=s.awaiting_reply,
        )


class ConversationSchema(BaseModel):
    contact: ContactSchema
    messages: list[MessageSchema]
    handover: HandoverSchema | None
    can_send_text: bool
    window_closes_at: datetime | None

    @classmethod
    def of(cls, d: ConversationDetail) -> ConversationSchema:
        return cls(
            contact=ContactSchema.of(d.contact),
            messages=[MessageSchema.of(m) for m in d.messages],
            handover=HandoverSchema.of(d.handover),
            can_send_text=d.can_send_text,
            window_closes_at=d.window_closes_at,
        )


class ReplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


@dataclass(frozen=True)
class InboxUseCases:
    list_inbox: ListInbox
    get_conversation: GetConversation
    handovers: Handovers
    reply: StaffReply


def build_router(for_tenant: Callable[[TenantId], InboxUseCases]) -> APIRouter:
    router = APIRouter(prefix="/inbox", tags=["inbox"])

    @router.get("")
    async def list_inbox(
        ctx: CanRead, limit: Annotated[int, Query(ge=1, le=200)] = 50
    ) -> list[ConversationSummarySchema]:
        rows = await for_tenant(ctx.tenant_id).list_inbox(ctx.tenant_id, ctx.actor, limit)
        return [ConversationSummarySchema.of(r) for r in rows]

    @router.get("/{contact_id}")
    async def conversation(contact_id: UUID, ctx: CanRead) -> ConversationSchema:
        detail = await for_tenant(ctx.tenant_id).get_conversation(
            ctx.tenant_id, contact_id, ctx.actor
        )
        return ConversationSchema.of(detail)

    @router.post("/{contact_id}/takeover")
    async def take_over(contact_id: UUID, ctx: CanReply) -> HandoverSchema:
        handover = await for_tenant(ctx.tenant_id).handovers.take_over(
            ctx.tenant_id, contact_id, ctx.principal.user_id
        )
        result = HandoverSchema.of(handover)
        assert result is not None
        return result

    @router.post("/{contact_id}/handback", status_code=status.HTTP_204_NO_CONTENT)
    async def hand_back(contact_id: UUID, ctx: CanReply) -> None:
        await for_tenant(ctx.tenant_id).handovers.hand_back(contact_id, ctx.principal.user_id)

    @router.post("/{contact_id}/reply")
    async def reply(contact_id: UUID, body: ReplyRequest, ctx: CanReply) -> dict[str, bool]:
        sent = await for_tenant(ctx.tenant_id).reply(
            ReplyCommand(ctx.tenant_id, contact_id, ctx.principal.user_id, body.text)
        )
        return {"sent": sent}

    return router
