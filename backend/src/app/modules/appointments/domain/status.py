"""Appointment status lifecycle (PRD §7.6).

[REQUESTED] --approve--> [CONFIRMED] --reschedule--> [RESCHEDULED] (again)
    |  decline -> DECLINED     |                           |
    |  expire  -> EXPIRED      +-- cancel / complete / no-show --+
    +- withdraw -> CANCELLED
"""

from __future__ import annotations

from enum import StrEnum


class AppointmentStatus(StrEnum):
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    RESCHEDULED = "rescheduled"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


S = AppointmentStatus

#: Hold a slot and count as "upcoming" (greeting rules R2/R5, case closing AP-10.3).
ACTIVE = frozenset({S.REQUESTED, S.CONFIRMED, S.RESCHEDULED})
#: Confirmed by the clinic (a REQUESTED appointment is not yet).
BOOKED = frozenset({S.CONFIRMED, S.RESCHEDULED})
FINAL = frozenset(S) - ACTIVE

ALLOWED: dict[AppointmentStatus, frozenset[AppointmentStatus]] = {
    S.REQUESTED: frozenset({S.CONFIRMED, S.DECLINED, S.EXPIRED, S.CANCELLED}),
    S.CONFIRMED: frozenset({S.RESCHEDULED, S.CANCELLED, S.COMPLETED, S.NO_SHOW}),
    S.RESCHEDULED: frozenset({S.RESCHEDULED, S.CANCELLED, S.COMPLETED, S.NO_SHOW}),
}
