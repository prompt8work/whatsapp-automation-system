from __future__ import annotations

from app.shared.module import ModuleDefinition

# The tick router is built explicitly by bootstrap (see wiring.py). No permissions: the
# tick endpoint is protected by the cron secret, not by user roles.
module = ModuleDefinition(key="jobs")
