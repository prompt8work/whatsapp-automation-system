from __future__ import annotations

from app.platform.inbox.infrastructure.sql import handovers
from app.platform.inbox.wiring import build_routers
from app.shared.infrastructure.forget import CONTACT_FORGOTTEN, forget_rows_in
from app.shared.kernel.roles import Role
from app.shared.module import ModuleDefinition

module = ModuleDefinition(
    key="inbox",
    build_routers=build_routers,
    permissions={
        "inbox.read": "See WhatsApp conversations",
        "inbox.reply": "Take over chats from the bot and reply",
    },
    role_grants={Role.STAFF: {"inbox.read", "inbox.reply"}},
    event_handlers={CONTACT_FORGOTTEN: [forget_rows_in(handovers)]},  # retention RT-4
    live_topics={e: ("inbox",) for e in ("HandoverRequested", "HandoverTaken", "HandoverEnded")},
)
