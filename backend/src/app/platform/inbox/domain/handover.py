"""Handover: a person is (or should be) handling a contact's chat, so the bot stays silent
(PRD PL-5.2, R8). At most one active handover per contact (enforced by a unique index).

    requested by the bot / contact ("AGENT", 3 failed answers)  -> active, nobody assigned yet
    taken over by staff                                         -> active, assigned
    handed back                                                 -> ended, the bot resumes
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.platform.inbox.domain.events import HandoverEnded, HandoverRequested, HandoverTaken
from app.shared.kernel.entity import TenantAggregateRoot
from app.shared.kernel.ids import TenantId


@dataclass(kw_only=True, eq=False)
class Handover(TenantAggregateRoot):
    contact_id: UUID
    reason: str  # "contact" (asked for a person), "bot" (could not help), "staff"
    started_at: datetime
    assigned_user_id: UUID | None = None
    ended_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @classmethod
    def request(
        cls, *, id: UUID, tenant_id: TenantId, contact_id: UUID, reason: str, at: datetime
    ) -> Handover:
        handover = cls(
            id=id, tenant_id=tenant_id, contact_id=contact_id, reason=reason, started_at=at
        )
        handover.record(HandoverRequested(occurred_at=at, contact_id=contact_id, reason=reason))
        return handover

    def take_over(self, user_id: UUID, at: datetime) -> None:
        if self.assigned_user_id != user_id:
            self.assigned_user_id = user_id
            self.record(HandoverTaken(occurred_at=at, contact_id=self.contact_id, user_id=user_id))

    def hand_back(self, user_id: UUID | None, at: datetime) -> None:
        if self.ended_at is None:
            self.ended_at = at
            self.record(HandoverEnded(occurred_at=at, contact_id=self.contact_id, user_id=user_id))
