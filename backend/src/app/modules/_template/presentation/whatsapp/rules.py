"""Router rules: when a NEW conversation starts, which flow runs (PRD §7.1).

Rules are checked in `priority` order (lower first) across all enabled modules; the first
one that returns a flow key wins. Keep each rule one small condition.
"""

from __future__ import annotations

from app.shared.application.conversation import FlowContext

KEYWORDS = {"item", "new item", "add item"}


class NewItemKeywordRule:
    module_key = "_template"
    priority = 500

    async def flow_for(self, ctx: FlowContext) -> str | None:
        return "_template.create_item" if ctx.reply.normalized in KEYWORDS else None
