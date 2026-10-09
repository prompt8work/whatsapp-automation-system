from __future__ import annotations

from app.shared.module import ModuleDefinition

# The webhook router and the safety-net job need the full module list and the tenancy
# facade, so app/main.py wires them via conversations/wiring.py:build_conversations.
module = ModuleDefinition(key="conversations")
