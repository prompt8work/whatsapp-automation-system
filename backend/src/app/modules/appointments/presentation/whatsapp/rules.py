"""Which appointments flow starts a NEW conversation (PRD §7.1).

R8 (staff handling the chat), R7 (flow interrupted) and STOP/START/MENU/AGENT are handled by
the platform before these rules run. R11: any first message - greeting or not - is routed
like a greeting, so these rules ignore the text.
"""

from __future__ import annotations

from app.modules.appointments.presentation.whatsapp.steps import BOOK, MENU, Bot
from app.shared.application.conversation import FlowContext


class ReturningContactRule:
    """R2 / R3 / R4 / R5 / R10: someone we know -> the menu (it adapts to their situation)."""

    module_key = "appointments"
    priority = 100

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def flow_for(self, ctx: FlowContext) -> str | None:
        if ctx.contact.is_new:
            return None
        if await self.bot.uc(ctx).patients_of_contact(ctx.contact.id):
            return MENU
        return None


class NewContactRule:
    """R1: a new number (or one that never finished booking) -> welcome + booking."""

    module_key = "appointments"
    priority = 900

    async def flow_for(self, ctx: FlowContext) -> str | None:
        ctx.say(
            ctx.t(
                "appointments.welcome.new" if ctx.contact.is_new else "appointments.welcome.again"
            )
        )
        return BOOK
