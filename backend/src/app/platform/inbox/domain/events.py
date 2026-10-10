from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.shared.kernel.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class HandoverRequested(DomainEvent):
    contact_id: UUID
    reason: str


@dataclass(frozen=True, kw_only=True)
class HandoverTaken(DomainEvent):
    contact_id: UUID
    user_id: UUID


@dataclass(frozen=True, kw_only=True)
class HandoverEnded(DomainEvent):
    contact_id: UUID
    user_id: UUID | None
