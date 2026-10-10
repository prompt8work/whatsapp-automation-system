"""Appointment aggregate - the status lifecycle of PRD §7.6 lives here and only here.

Every method takes `by: By` (actor, channel, time) and records an event, so the history
(PRD §7.8) is complete by construction. Slot availability is checked BEFORE calling these
methods (availability service + slot reservations); this class guards the rules that only
depend on the appointment itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.modules.appointments.domain.errors import (
    InvalidTransitionError,
    NoPendingChangeError,
    SameSlotError,
)
from app.modules.appointments.domain.events import (
    AppointmentCancelled,
    AppointmentCompleted,
    AppointmentConfirmed,
    AppointmentDeclined,
    AppointmentDetailsUpdated,
    AppointmentExpired,
    AppointmentNoShow,
    AppointmentRequested,
    AppointmentRescheduled,
    RescheduleDeclined,
    RescheduleRequested,
)
from app.modules.appointments.domain.status import ACTIVE, ALLOWED, BOOKED, AppointmentStatus
from app.modules.appointments.domain.values import By, Slot
from app.shared.kernel.entity import TenantAggregateRoot
from app.shared.kernel.ids import TenantId

S = AppointmentStatus


@dataclass(kw_only=True, eq=False)
class Appointment(TenantAggregateRoot):
    reference: str
    case_id: UUID
    patient_id: UUID
    contact_id: UUID
    location_id: UUID
    slot: Slot
    original_slot: Slot
    status: AppointmentStatus
    created_at: datetime
    reason: str = ""
    fields: dict[str, Any] = field(default_factory=dict)
    pending_slot: Slot | None = None  # a reschedule waiting for the clinic (AP-4.4)
    pending_since: datetime | None = None

    # ------------------------------------------------------------------ creation
    @classmethod
    def book(
        cls,
        *,
        id: UUID,
        tenant_id: TenantId,
        reference: str,
        case_id: UUID,
        patient_id: UUID,
        contact_id: UUID,
        location_id: UUID,
        slot: Slot,
        reason: str,
        fields: dict[str, Any],
        needs_approval: bool,
        by: By,
    ) -> Appointment:
        """REQUESTED when the clinic approves bookings (default), else CONFIRMED (AP-2.5)."""
        appt = cls(
            id=id,
            tenant_id=tenant_id,
            reference=reference,
            case_id=case_id,
            patient_id=patient_id,
            contact_id=contact_id,
            location_id=location_id,
            slot=slot,
            original_slot=slot,
            status=S.REQUESTED,
            created_at=by.at,
            reason=reason,
            fields=dict(fields),
        )
        appt.record(
            AppointmentRequested(
                **appt._who(by),
                case_id=case_id,
                patient_id=patient_id,
                doctor_id=slot.doctor_id,
                start=slot.start,
                end=slot.end,
                needs_approval=needs_approval,
            )
        )
        if not needs_approval:
            appt._move(S.CONFIRMED)
            appt.record(AppointmentConfirmed(**appt._who(by), automatic=True))
        return appt

    def reassign_reference(self, reference: str) -> None:
        """Only before the first save, when the random reference clashed with another one."""
        self.reference = reference

    # ------------------------------------------------------------------ queries
    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE

    @property
    def doctor_id(self) -> UUID:
        return self.slot.doctor_id

    @property
    def was_rescheduled(self) -> bool:
        return self.slot != self.original_slot

    # ------------------------------------------------------------------ clinic decisions
    def approve(self, by: By) -> None:
        self._move(S.CONFIRMED, allowed_from={S.REQUESTED})
        self.record(AppointmentConfirmed(**self._who(by), automatic=False))

    def decline(self, reason: str, by: By) -> None:
        self._move(S.DECLINED, allowed_from={S.REQUESTED})
        self.record(AppointmentDeclined(**self._who(by), reason=reason.strip()[:300]))

    def expire(self, by: By) -> None:
        self._move(S.EXPIRED, allowed_from={S.REQUESTED})
        self.record(AppointmentExpired(**self._who(by)))

    # ------------------------------------------------------------------ changes
    def request_reschedule(self, new_slot: Slot, by: By) -> None:
        """Approval mode: hold the new slot, keep the current one valid until the clinic
        decides (AP-4.4)."""
        self._ensure_can_change(new_slot)
        if self.status is S.REQUESTED:
            self.reschedule(new_slot, by)  # an unconfirmed request is simply changed
            return
        self.pending_slot, self.pending_since = new_slot, by.at
        self.record(
            RescheduleRequested(
                **self._who(by),
                current_start=self.slot.start,
                requested_start=new_slot.start,
                requested_end=new_slot.end,
                doctor_id=new_slot.doctor_id,
            )
        )

    def reschedule(self, new_slot: Slot, by: By) -> None:
        """Move now (no approval needed, or staff doing it). Same id and reference (AP-4.6)."""
        self._ensure_can_change(new_slot)
        old = self.slot
        if self.status is not S.REQUESTED:
            self._move(S.RESCHEDULED)
        self.slot = new_slot
        self.pending_slot = self.pending_since = None
        self.record(self._rescheduled(old, new_slot, by))

    def approve_reschedule(self, by: By) -> Slot:
        """Returns the slot that was given up (its reservation must be released)."""
        if self.pending_slot is None:
            raise NoPendingChangeError()
        old, new = self.slot, self.pending_slot
        self._move(S.RESCHEDULED)
        self.slot = new
        self.pending_slot = self.pending_since = None
        self.record(self._rescheduled(old, new, by))
        return old

    def decline_reschedule(self, reason: str, by: By) -> Slot:
        """Returns the held slot (its reservation must be released). Appointment unchanged."""
        if self.pending_slot is None:
            raise NoPendingChangeError()
        held = self.pending_slot
        self.pending_slot = self.pending_since = None
        self.record(
            RescheduleDeclined(
                **self._who(by), requested_start=held.start, reason=reason.strip()[:300]
            )
        )
        return held

    def cancel(self, reason: str, by: By) -> list[Slot]:
        """Returns every slot this appointment held (current + pending) to release."""
        self._move(S.CANCELLED)
        released = [self.slot, *([self.pending_slot] if self.pending_slot else [])]
        self.pending_slot = self.pending_since = None
        self.record(AppointmentCancelled(**self._who(by), reason=reason.strip()[:300]))
        return released

    def complete(self, by: By) -> None:
        self._ensure_started(by.at)
        self._move(S.COMPLETED)
        self.record(AppointmentCompleted(**self._who(by)))

    def mark_no_show(self, by: By) -> None:
        self._ensure_started(by.at)
        self._move(S.NO_SHOW)
        self.record(AppointmentNoShow(**self._who(by)))

    def update_details(self, *, reason: str | None, fields: dict[str, Any] | None, by: By) -> None:
        changed: list[str] = []
        if reason is not None and reason != self.reason:
            self.reason, changed = reason, [*changed, "reason"]
        if fields is not None and fields != self.fields:
            changed += sorted(
                k for k in fields.keys() | self.fields.keys() if fields.get(k) != self.fields.get(k)
            )
            self.fields = dict(fields)
        if changed:
            self.record(AppointmentDetailsUpdated(**self._who(by), changed=tuple(changed)))

    # ------------------------------------------------------------------ helpers
    def _who(self, by: By) -> dict[str, Any]:
        return {
            "occurred_at": by.at,
            "appointment_id": self.id,
            "actor": by.actor,
            "channel": by.channel,
        }

    def _move(
        self, to: AppointmentStatus, *, allowed_from: set[AppointmentStatus] | None = None
    ) -> None:
        if (allowed_from is not None and self.status not in allowed_from) or to not in ALLOWED.get(
            self.status, frozenset()
        ):
            raise InvalidTransitionError(f"Cannot go from {self.status} to {to}")
        self.status = to

    def _ensure_can_change(self, new_slot: Slot) -> None:
        if not self.is_active:
            raise InvalidTransitionError(f"A {self.status} appointment cannot be changed")
        if new_slot == self.slot:
            raise SameSlotError("That is already the appointment time")

    def _ensure_started(self, now: datetime) -> None:
        if self.status not in BOOKED:
            raise InvalidTransitionError(f"A {self.status} appointment cannot be marked")
        if now < self.slot.start:
            raise InvalidTransitionError("The appointment has not started yet")

    def _rescheduled(self, old: Slot, new: Slot, by: By) -> AppointmentRescheduled:
        return AppointmentRescheduled(
            **self._who(by),
            old_start=old.start,
            old_end=old.end,
            new_start=new.start,
            new_end=new.end,
            old_doctor_id=old.doctor_id,
            new_doctor_id=new.doctor_id,
        )
