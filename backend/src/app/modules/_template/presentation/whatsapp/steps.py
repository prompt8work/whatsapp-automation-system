"""Steps: each asks ONE question and handles the answer (ARCHITECTURE §7.3).

A step never touches repositories - it calls the SAME use cases the HTTP routers call.
"""

from __future__ import annotations

from collections.abc import Callable

from app.modules._template.application.commands.create_item import CreateItemCommand
from app.modules._template.application.use_cases import ItemUseCases
from app.modules._template.domain.errors import InvalidItemNameError
from app.shared.application.conversation import (
    BaseStep,
    Finish,
    FlowContext,
    InboundReply,
    Retry,
    StepResult,
)
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId


class AskItemName(BaseStep):
    key = "ask_name"

    def __init__(self, use_cases_for: Callable[[TenantId], ItemUseCases]) -> None:
        self._use_cases_for = use_cases_for

    async def should_skip(self, ctx: FlowContext) -> bool:
        return "item_name" in ctx.data  # DR-5: never ask for what we already have

    async def prompt(self, ctx: FlowContext) -> None:
        ctx.say(ctx.t("_template.ask_name"))

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        try:
            item = await self._use_cases_for(ctx.tenant_id).create(
                CreateItemCommand(name=reply.text, actor=Actor.contact(ctx.contact.id))
            )
        except InvalidItemNameError:
            return Retry("_template.invalid_name")
        ctx.data["item_name"] = item.name
        ctx.say(ctx.t("_template.created", name=item.name))
        return Finish()
