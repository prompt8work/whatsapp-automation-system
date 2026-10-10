"""The inbound pipeline for ONE message (PRD PL-3.2, ARCHITECTURE §7.1):

    lock session -> staff handover? -> global command? -> continue flow | route new conversation

Replies are collected in ctx.outbox and sent AFTER the session is committed, so a crash can
never leave the person with an answer the system does not remember giving.
"""

from __future__ import annotations

from collections.abc import Callable

from app.platform.conversations.application.engine import FlowEngine, Router
from app.platform.conversations.application.ports import ContactGateway, HandoverDesk
from app.platform.conversations.application.unit_of_work import ConversationsUnitOfWork
from app.platform.conversations.domain.session import ConversationSession
from app.platform.messaging.contracts import InboundKind, InboundMessage
from app.platform.tenancy.contracts import TenantRoute
from app.shared.application.conversation import ContactInfo, FlowContext, InboundReply, Translator
from app.shared.application.messaging import Messenger, SendRequest
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId
from app.shared.kernel.messages import Buttons, Choice

STOP_WORDS = {"stop", "unsubscribe"}
START_WORDS = {"start", "subscribe"}
MENU_WORDS = {"menu", "restart", "main menu"}
AGENT_WORDS = {"agent", "human", "talk to staff", "talk to someone"}
CONTINUE, RESTART = "conversations:continue", "conversations:restart"


class HandleInboundMessage:
    def __init__(
        self,
        uow_for: Callable[[TenantId], ConversationsUnitOfWork],
        engine: FlowEngine,
        router: Router,
        contacts: ContactGateway,
        messenger: Messenger,
        handover: HandoverDesk,
        translator: Translator,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow_for, self._engine, self._router = uow_for, engine, router
        self._contacts, self._messenger, self._handover = contacts, messenger, handover
        self._translator, self._clock, self._ids = translator, clock, ids

    async def __call__(
        self, route: TenantRoute, contact: ContactInfo, message: InboundMessage
    ) -> None:
        now = self._clock.now()
        tenant_id = route.tenant_id
        reply = InboundReply(
            text=message.text,
            choice_id=message.choice_id,
            is_supported=message.kind is not InboundKind.UNSUPPORTED,
        )
        async with self._uow_for(tenant_id) as uow:
            session = await uow.sessions.lock_and_get(contact.id) or ConversationSession.new(
                id=self._ids.new_id(), tenant_id=tenant_id, contact_id=contact.id, at=now
            )
            ctx = FlowContext(
                tenant_id=tenant_id,
                contact=contact,
                reply=reply,
                data=session.data,
                translator=self._translator,
                now=now,
                enabled_modules=route.enabled_modules,
            )
            if await self._handover.is_active(tenant_id, contact.id):
                pass  # R8: a staff member is handling this chat - the bot stays silent
            elif not await self._global_command(ctx, session):
                handled = session.is_active(now) and await self._engine.reply(ctx, session)
                if not handled:
                    await self._route(ctx, session)
            await uow.sessions.save(session)
            await uow.commit()

        for outbound in ctx.outbox:
            await self._messenger.send(
                SendRequest(
                    tenant_id, contact.id, contact.phone, message.phone_number_id, outbound, now
                )
            )
        if ctx.handover_requested:
            await self._handover.request(tenant_id, contact.id, reason="bot")

    async def _route(self, ctx: FlowContext, session: ConversationSession) -> None:
        flow_key = await self._router.flow_for(ctx)
        if flow_key:
            await self._engine.start(ctx, session, flow_key)
        else:
            ctx.say(ctx.t("conversations.fallback"))

    async def _global_command(self, ctx: FlowContext, session: ConversationSession) -> bool:
        """Commands that work anywhere, in any flow (PRD PL-3.5, PL-2.4)."""
        word = ctx.reply.normalized
        if word in STOP_WORDS:
            await self._contacts.set_opt_out(ctx.tenant_id, ctx.contact.id, True)
            ctx.say(ctx.t("conversations.opted_out"))
        elif word in START_WORDS:
            await self._contacts.set_opt_out(ctx.tenant_id, ctx.contact.id, False)
            ctx.say(ctx.t("conversations.opted_in"))
        elif word in MENU_WORDS:
            session.finish(ctx.now)
            await self._route(ctx, session)
        elif word in AGENT_WORDS:
            session.finish(ctx.now)
            ctx.say(ctx.t("conversations.agent_requested"))
            ctx.request_handover()
        elif ctx.reply.choice_id == RESTART:
            session.finish(ctx.now)
            await self._route(ctx, session)
        elif ctx.reply.choice_id == CONTINUE:
            if not await self._engine.reprompt(ctx, session):
                session.finish(ctx.now)
                await self._route(ctx, session)
        elif session.is_active(ctx.now) and ctx.reply.is_greeting:
            # R7: "Hi" in the middle of a flow - offer to continue instead of failing the step.
            ctx.say(
                Buttons(
                    ctx.t("conversations.resume.ask"),
                    (
                        Choice(CONTINUE, ctx.t("conversations.resume.continue")),
                        Choice(RESTART, ctx.t("conversations.resume.restart")),
                    ),
                )
            )
            session.touch(ctx.now)
        else:
            return False
        return True
