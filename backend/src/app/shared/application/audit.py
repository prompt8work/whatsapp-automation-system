"""Audit port (PRD PL-8.3): record who read or changed personal data.

Use cases that return or change personal data call it explicitly:

    await self._audit.record(AuditRecord.of(principal, "contact.read", "contact", contact_id))

Records must never contain the personal data itself - only ids and action names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId


@dataclass(frozen=True)
class AuditRecord:
    tenant_id: TenantId
    actor: Actor
    action: str  # e.g. "contact.read", "contact.opt_out"
    resource_type: str  # e.g. "contact"
    resource_id: UUID | None = None
    details: dict[str, Any] = field(default_factory=dict)  # ids/counts only, never PII


class AuditLogger(Protocol):
    async def record(self, entry: AuditRecord) -> None: ...
