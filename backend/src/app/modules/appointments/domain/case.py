"""Case: one treatment episode grouping a patient's appointments (PRD §7.10).

OPEN -> CLOSED (by staff, only when nothing is upcoming) -> deleted by retention
(infrastructure/purge.py - a purged case simply no longer exists).
A closed case can be reopened until it is purged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from app.modules.appointments.domain.errors import (
    CaseClosedError,
    CaseHasActiveAppointmentsError,
)
from app.modules.appointments.domain.events import CaseClosed, CaseOpened, CaseReopened
from app.shared.kernel.actor import Actor
from app.shared.kernel.entity import TenantAggregateRoot
from app.shared.kernel.ids import TenantId


class CaseStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass(kw_only=True, eq=False)
class Case(TenantAggregateRoot):
    patient_id: UUID
    opened_at: datetime
    last_activity_at: datetime  # retention RT-2: incomplete cases purge 12 months after this
    status: CaseStatus = CaseStatus.OPEN
    closed_at: datetime | None = None  # retention RT-1: closed cases purge 60 days after this
    closing_note: str = ""
    legal_hold: bool = False  # RT-6: never purged while set

    @classmethod
    def open(cls, *, id: UUID, tenant_id: TenantId, patient_id: UUID, at: datetime) -> Case:
        case = cls(
            id=id, tenant_id=tenant_id, patient_id=patient_id, opened_at=at, last_activity_at=at
        )
        case.record(CaseOpened(occurred_at=at, case_id=id, patient_id=patient_id))
        return case

    @property
    def is_open(self) -> bool:
        return self.status is CaseStatus.OPEN

    def touch(self, at: datetime) -> None:
        """Any booking/change in this case counts as activity."""
        if not self.is_open:
            raise CaseClosedError("This case is closed; reopen it or start a new one")
        self.last_activity_at = max(self.last_activity_at, at)

    def close(self, *, active_appointments: int, note: str, actor: Actor, at: datetime) -> None:
        if not self.is_open:
            return
        if active_appointments:
            raise CaseHasActiveAppointmentsError(
                f"Cancel or complete the {active_appointments} upcoming appointment(s) first"
            )
        self.status = CaseStatus.CLOSED
        self.closed_at = at
        self.closing_note = note.strip()[:500]
        self.record(CaseClosed(occurred_at=at, case_id=self.id, actor=actor))

    def reopen(self, *, actor: Actor, at: datetime) -> None:
        if self.is_open:
            return
        self.status = CaseStatus.OPEN
        self.closed_at = None  # RT-5: the 60-day countdown restarts on the next close
        self.last_activity_at = at
        self.record(CaseReopened(occurred_at=at, case_id=self.id, actor=actor))

    def set_legal_hold(self, hold: bool) -> None:
        self.legal_hold = hold

    def deletes_at(self, *, closed_after: timedelta, open_after: timedelta) -> datetime | None:
        """When retention will delete it (AP-10.6). None on legal hold. An active appointment
        postpones it further (RT-6) - this is the earliest possible date."""
        if self.legal_hold:
            return None
        if self.closed_at is not None:
            return self.closed_at + closed_after
        return self.last_activity_at + open_after
