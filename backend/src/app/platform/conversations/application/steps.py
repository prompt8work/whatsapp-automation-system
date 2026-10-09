"""Reusable steps any module can put in its flows."""

from __future__ import annotations

from app.platform.conversations.application.ports import ContactGateway
from app.shared.application.conversation import (
    BaseStep,
    Finish,
    FlowContext,
    InboundReply,
    Next,
    Retry,
    StepResult,
)
from app.shared.kernel.messages import Buttons, Choice

YES, NO = "consent:yes", "consent:no"


class AskConsent(BaseStep):
    """PRD PL-2.4 / R1: ask once before saving anything about a new contact."""

    key = "consent"

    def __init__(self, contacts: ContactGateway) -> None:
        self._contacts = contacts

    async def should_skip(self, ctx: FlowContext) -> bool:
        return ctx.contact.has_consent or ctx.data.get("consent") is True

    async def prompt(self, ctx: FlowContext) -> None:
        ctx.say(
            Buttons(
                ctx.t("conversations.consent.ask"),
                (
                    Choice(YES, ctx.t("conversations.consent.yes")),
                    Choice(NO, ctx.t("conversations.consent.no")),
                ),
            )
        )

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        if reply.choice_id == YES or reply.normalized in {"yes", "y", "ok", "okay", "haan"}:
            await self._contacts.grant_consent(ctx.tenant_id, ctx.contact.id)
            ctx.data["consent"] = True
            return Next()
        if reply.choice_id == NO or reply.normalized in {"no", "n", "nahi"}:
            ctx.say(ctx.t("conversations.consent.declined"))
            return Finish()
        return Retry("conversations.consent.retry")
