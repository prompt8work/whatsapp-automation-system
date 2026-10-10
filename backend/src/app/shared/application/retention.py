"""Retention port (PRD §7.10, ARCHITECTURE §8.7). Every module that keeps personal data
provides a Purger; the platform's daily retention job runs them for every tenant.

Purges delete for real (no "deleted" flag) and run with the separate `app_purge` database role,
the only one allowed to delete append-only history. Results contain counts only - never
personal data - and are kept as deletion records (AP-10.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.shared.kernel.ids import TenantId


@dataclass(frozen=True)
class PurgeTarget:
    subject_type: str  # e.g. "case"
    subject_id: UUID
    rule: str  # "RT-1", "RT-2", "RT-4", "AP-10.11" (PRD §7.10)
    due_at: datetime
    # For the staff "deleting soon" list only (e.g. the patient's name). Never stored.
    label: str = ""


@dataclass(frozen=True)
class PurgeResult:
    counts: dict[str, int] = field(default_factory=dict)  # e.g. {"appointments": 3, "cases": 1}


class Purger(Protocol):
    key: str  # e.g. "appointments.cases"

    async def due(self, tenant_id: TenantId, until: datetime) -> list[PurgeTarget]:
        """Everything that will be due for deletion by `until` (now -> due now; now+7d ->
        the "deleting soon" list, AP-10.6). Must exclude legal holds and RT-6 blocks."""
        ...

    async def purge(self, tenant_id: TenantId, target: PurgeTarget) -> PurgeResult: ...
