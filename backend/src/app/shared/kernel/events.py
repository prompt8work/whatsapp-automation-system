"""Domain events.

An aggregate records an event for every business change. On commit the Unit of Work
writes the events to the outbox (and, for modules with history, to their history table)
in the SAME transaction as the state change - ARCHITECTURE §8.4, ADR-003.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.shared.kernel.ids import uuid7


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    occurred_at: datetime
    event_id: UUID = field(default_factory=uuid7)

    @property
    def event_type(self) -> str:
        return type(self).__name__
