from __future__ import annotations

from app.platform.retention.application.use_cases import RUN_JOB
from app.shared.kernel.roles import Role
from app.shared.module import ModuleDefinition

# The job handler and router need every module's purgers: bootstrap/platform.py wires them.
module = ModuleDefinition(
    key="retention",
    permissions={"retention.read": "See scheduled and completed data deletions"},
    role_grants={Role.STAFF: {"retention.read"}},
    daily_jobs={RUN_JOB: 20},  # 20:00 UTC = 01:30 IST, after the clinic day everywhere in India
)
