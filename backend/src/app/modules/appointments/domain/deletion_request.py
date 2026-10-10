"""Deletion Request: a patient asked on WhatsApp to delete their data (PRD AP-10.8-10.13).

PENDING -> COMPLETED (staff approved; the data is gone) | REJECTED (with a reason).
Holds ids only: after completion it is the request's own record, with nothing personal in it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from app.modules.appointments.domain.errors import (
    DeletionRequestDecidedError,
    RejectionReasonRequiredError,
)
from app.modules.appointments.domain.events import (
    DeletionRequestCompleted,
    DeletionRequested,
    DeletionRequestRejected,
)
from app.shared.kernel.actor import Actor
from app.shared.kernel.entity import TenantAggregateRoot
from app.shared.kernel.ids import TenantId

ANSWER_WITHIN = timedelta(days=7)  # AP-10.10 default


class DeletionStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    REJECTED = "rejected"


@dataclass(kw_only=True, eq=False)
class DeletionRequest(TenantAggregateRoot):
    contact_id: UUID
    patient_ids: tuple[UUID, ...]  # AP-10.12: one patient of the number, or all of them
    requested_at: datetime
    status: DeletionStatus = DeletionStatus.PENDING
    decided_at: datetime | None = None
    decided_by: UUID | None = None
    rejection_reason: str = ""
    deleted_counts: dict[str, int] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: TenantId,
        contact_id: UUID,
        patient_ids: tuple[UUID, ...],
        at: datetime,
    ) -> DeletionRequest:
        request = cls(
            id=id,
            tenant_id=tenant_id,
            contact_id=contact_id,
            patient_ids=patient_ids,
            requested_at=at,
        )
        request.record(DeletionRequested(occurred_at=at, request_id=id, contact_id=contact_id))
        return request

    @property
    def answer_by(self) -> datetime:
        return self.requested_at + ANSWER_WITHIN

    def ensure_pending(self) -> None:
        if self.status is not DeletionStatus.PENDING:
            raise DeletionRequestDecidedError(f"This request was already {self.status.value}")

    def reject(self, *, reason: str, actor: Actor, at: datetime) -> None:
        self.ensure_pending()
        cleaned = " ".join(reason.split())[:500]
        if not cleaned:
            raise RejectionReasonRequiredError("Tell the patient why (e.g. an upcoming visit)")
        self.status, self.decided_at, self.decided_by = DeletionStatus.REJECTED, at, actor.id
        self.rejection_reason = cleaned
        self.record(
            DeletionRequestRejected(
                occurred_at=at,
                request_id=self.id,
                contact_id=self.contact_id,
                reason=cleaned,
                actor=actor,
            )
        )

    def complete(self, *, counts: dict[str, int], actor: Actor, at: datetime) -> None:
        self.ensure_pending()
        self.status, self.decided_at, self.decided_by = DeletionStatus.COMPLETED, at, actor.id
        self.deleted_counts = dict(counts)
        self.record(
            DeletionRequestCompleted(
                occurred_at=at, request_id=self.id, contact_id=self.contact_id, actor=actor
            )
        )
