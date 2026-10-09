"""A stored audit entry (read side). Entries are written via the shared AuditLogger port and
are append-only: the API's database role cannot UPDATE or DELETE them (PRD §11)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class AuditEntry:
    id: UUID
    actor_kind: str
    actor_id: UUID | None
    action: str
    resource_type: str
    resource_id: UUID | None
    details: dict[str, Any]
    at: datetime
