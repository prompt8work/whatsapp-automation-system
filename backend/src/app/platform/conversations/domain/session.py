"""Conversation session: where one contact is in a flow (PRD PL-3.1).

One row per contact, reused. Idle sessions expire after 24 h - the next message then starts
a fresh conversation through the router (R7 "continue or start over" is a module rule that
can look at `last_flow_key`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from app.shared.kernel.entity import TenantAggregateRoot
from app.shared.kernel.ids import TenantId

SESSION_TTL = timedelta(hours=24)


@dataclass(kw_only=True, eq=False)
class ConversationSession(TenantAggregateRoot):
    contact_id: UUID
    updated_at: datetime
    flow_key: str | None = None
    step_key: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0  # failed answers at the current step
    expires_at: datetime | None = None
    last_flow_key: str | None = None  # the most recent flow, even after it ended

    @classmethod
    def new(
        cls, *, id: UUID, tenant_id: TenantId, contact_id: UUID, at: datetime
    ) -> ConversationSession:
        return cls(id=id, tenant_id=tenant_id, contact_id=contact_id, updated_at=at)

    def is_active(self, now: datetime) -> bool:
        return self.flow_key is not None and self.expires_at is not None and now < self.expires_at

    def begin(self, flow_key: str, now: datetime) -> None:
        self.flow_key = flow_key
        self.last_flow_key = flow_key
        self.step_key = None
        self.data = {}
        self.attempts = 0
        self.touch(now)

    def at_step(self, step_key: str, now: datetime) -> None:
        if step_key != self.step_key:
            self.attempts = 0
        self.step_key = step_key
        self.touch(now)

    def failed_attempt(self) -> int:
        self.attempts += 1
        return self.attempts

    def finish(self, now: datetime) -> None:
        self.flow_key = None
        self.step_key = None
        self.data = {}
        self.attempts = 0
        self.expires_at = None
        self.updated_at = now

    def touch(self, now: datetime) -> None:
        self.updated_at = now
        self.expires_at = now + SESSION_TTL
