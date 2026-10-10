from __future__ import annotations

from app.platform.conversations.infrastructure.tables import conversation_sessions
from app.shared.infrastructure.forget import CONTACT_FORGOTTEN, forget_rows_in
from app.shared.module import ModuleDefinition

# The webhook router and the safety-net job need the full module list and the tenancy
# facade, so app/main.py wires them via conversations/wiring.py:build_conversations.
module = ModuleDefinition(
    key="conversations",
    event_handlers={CONTACT_FORGOTTEN: [forget_rows_in(conversation_sessions)]},  # RT-4
)
