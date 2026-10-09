"""Event handlers port (ARCHITECTURE §8.4).

Domain events are saved to the outbox on commit. The dispatcher (platform/jobs) later hands
each stored event to every handler registered for its type. Handlers receive the stored,
JSON form - not the original dataclass - because they run in a later request/process.

Handlers MUST be idempotent (use `event_id` as the idempotency key): delivery is at-least-once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.shared.kernel.ids import TenantId


@dataclass(frozen=True)
class StoredEvent:
    event_id: UUID
    event_type: str  # the DomainEvent class name, e.g. "ContactOptedOut"
    tenant_id: TenantId | None
    occurred_at: datetime
    payload: dict[str, Any]


class EventHandler(Protocol):
    async def __call__(self, event: StoredEvent) -> None: ...
