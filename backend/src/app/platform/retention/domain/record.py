"""Deletion record (PRD AP-10.5): proof that a purge happened - and NOTHING personal.

Ids of things that no longer exist, the rule applied and how many rows went. Never names,
phone numbers or health details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.shared.kernel.ids import TenantId


@dataclass(frozen=True)
class DeletionRecord:
    id: UUID
    tenant_id: TenantId
    purger: str  # e.g. "appointments.cases"
    subject_type: str  # e.g. "case"
    subject_id: UUID
    rule: str  # "RT-1", "RT-2", "RT-4", "AP-10.11"
    counts: dict[str, int] = field(default_factory=dict)
    at: datetime | None = None
