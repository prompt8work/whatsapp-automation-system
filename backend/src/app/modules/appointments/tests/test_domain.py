"""Domain rules: appointment lifecycle, availability, policy, doctors, cases. Pure Python."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest

from app.modules.appointments.domain.appointment import Appointment
from app.modules.appointments.domain.availability import free_slots, require_free_slot
from app.modules.appointments.domain.case import Case
from app.modules.appointments.domain.doctor import Doctor
from app.modules.appointments.domain.errors import (
    CaseHasActiveAppointmentsError,
    ChangeCutoffPassedError,
    InvalidBookingFieldsError,
    InvalidScheduleError,
    InvalidTransitionError,
    ReasonRequiredError,
    SameSlotError,
    SlotUnavailableError,
)
from app.modules.appointments.domain.events import (
    AppointmentConfirmed,
    AppointmentRequested,
    AppointmentRescheduled,
    RescheduleRequested,
)
from app.modules.appointments.domain.policy import BookingPolicy
from app.modules.appointments.domain.status import AppointmentStatus as S
from app.modules.appointments.domain.values import By, Slot, TimeOff, WorkingHours, new_reference
from app.shared.kernel.actor import Actor, Channel
from app.shared.kernel.ids import TenantId

TENANT = TenantId(UUID(int=1))
DOCTOR = UUID(int=2)
STAFF = Actor.staff(UUID(int=3))
PATIENT_ACTOR = Actor.contact(UUID(int=4))
NOW = datetime(2026, 10, 12, 4, 0, tzinfo=UTC)  # Mon 09:30 in Kolkata
IST = "Asia/Kolkata"


def by(actor: Actor = STAFF, at: datetime = NOW) -> By:
    return By(actor, Channel.DASHBOARD, at)


def slot(hours_from_now: float, minutes: int = 15) -> Slot:
    start = NOW + timedelta(hours=hours_from_now)
    return Slot(DOCTOR, start, start + timedelta(minutes=minutes))


def book(*, needs_approval: bool = True, at: Slot | None = None) -> Appointment:
    return Appointment.book(
        id=UUID(int=10),
        tenant_id=TENANT,
        reference="APT-TEST",
        case_id=UUID(int=11),
        patient_id=UUID(int=12),
        contact_id=UUID(int=13),
        location_id=UUID(int=14),
        slot=at or slot(24),
        reason="Fever",
        fields={},
        needs_approval=needs_approval,
        by=by(PATIENT_ACTOR),
    )


# ------------------------------------------------------------------ lifecycle (PRD §7.6)
def test_booking_needs_approval_by_default() -> None:
    appt = book()
    assert appt.status is S.REQUESTED
    assert [type(e) for e in appt.pull_events()] == [AppointmentRequested]


def test_auto_confirm_when_clinic_does_not_require_approval() -> None:
    appt = book(needs_approval=False)
    assert appt.status is S.CONFIRMED
    assert [type(e) for e in appt.pull_events()] == [AppointmentRequested, AppointmentConfirmed]


def test_reschedule_keeps_id_reference_and_original_time() -> None:  # PRD AC-6
    appt = book()
    appt.approve(by())
    first = appt.slot

    appt.reschedule(slot(48), by())

    assert (appt.id, appt.reference, appt.status) == (UUID(int=10), "APT-TEST", S.RESCHEDULED)
    assert appt.original_slot == first
    assert appt.was_rescheduled
    event = appt.pull_events()[-1]
    assert isinstance(event, AppointmentRescheduled)
    assert (event.old_start, event.new_start) == (first.start, appt.slot.start)


def test_reschedule_request_keeps_current_slot_until_approved() -> None:  # AP-4.4
    appt = book()
    appt.approve(by())
    current = appt.slot

    appt.request_reschedule(slot(48), by(PATIENT_ACTOR))
    assert appt.slot == current
    assert appt.pending_slot == slot(48)
    assert isinstance(appt.pull_events()[-1], RescheduleRequested)

    given_up = appt.approve_reschedule(by())
    assert given_up == current
    assert appt.slot == slot(48)
    assert appt.status is S.RESCHEDULED
    assert appt.pending_slot is None


def test_declined_reschedule_changes_nothing_and_releases_hold() -> None:
    appt = book()
    appt.approve(by())
    appt.request_reschedule(slot(48), by(PATIENT_ACTOR))

    held = appt.decline_reschedule("Doctor away", by())

    assert held == slot(48)
    assert (appt.slot, appt.pending_slot, appt.status) == (slot(24), None, S.CONFIRMED)


def test_changing_an_unconfirmed_request_just_moves_it() -> None:
    appt = book()
    appt.request_reschedule(slot(30), by(PATIENT_ACTOR))
    assert (appt.status, appt.slot, appt.pending_slot) == (S.REQUESTED, slot(30), None)


def test_cancel_returns_every_held_slot() -> None:
    appt = book()
    appt.approve(by())
    appt.request_reschedule(slot(48), by(PATIENT_ACTOR))
    assert appt.cancel("Feeling better", by(PATIENT_ACTOR)) == [slot(24), slot(48)]
    assert appt.status is S.CANCELLED


@pytest.mark.parametrize("final", ["decline", "expire", "cancel"])
def test_final_statuses_cannot_change(final: str) -> None:
    appt = book()
    if final == "decline":
        appt.decline("No", by())
    elif final == "expire":
        appt.expire(by(Actor.system()))
    else:
        appt.cancel("", by())
    with pytest.raises(InvalidTransitionError):
        appt.reschedule(slot(48), by())
    with pytest.raises(InvalidTransitionError):
        appt.approve(by())


def test_only_requests_can_be_approved_or_declined() -> None:
    appt = book(needs_approval=False)
    with pytest.raises(InvalidTransitionError):
        appt.approve(by())
    with pytest.raises(InvalidTransitionError):
        appt.decline("x", by())


def test_attendance_only_after_start_and_only_when_booked() -> None:
    appt = book()
    with pytest.raises(InvalidTransitionError):
        appt.complete(by(at=NOW + timedelta(days=2)))  # still REQUESTED
    appt.approve(by())
    with pytest.raises(InvalidTransitionError):
        appt.mark_no_show(by())  # not started yet
    appt.complete(by(at=appt.slot.start + timedelta(minutes=5)))
    assert appt.status is S.COMPLETED


def test_same_slot_is_rejected() -> None:
    appt = book()
    with pytest.raises(SameSlotError):
        appt.reschedule(appt.slot, by())


def test_references_are_short_and_unambiguous() -> None:
    refs = {new_reference() for _ in range(200)}
    assert all(r.startswith("APT-") and len(r) == 8 for r in refs)
    assert not any(c in r[4:] for r in refs for c in "ILOU")


# ------------------------------------------------------------------ availability (AP-2.3)
def doctor(**changes: object) -> Doctor:
    d = Doctor.add(
        id=DOCTOR,
        tenant_id=TENANT,
        location_id=UUID(int=14),
        name="Dr Amit",
        specialty="General",
        slot_minutes=15,
        actor=STAFF,
        at=NOW,
    )
    d.set_working_hours(
        [WorkingHours(day, time(9), time(10)) for day in range(7)], actor=STAFF, at=NOW
    )
    for key, value in changes.items():
        setattr(d, key, value)
    return d


TOMORROW = date(2026, 10, 13)


def test_slots_are_local_wall_clock_converted_to_utc() -> None:
    slots = free_slots(doctor(), TOMORROW, timezone=IST, busy=[], now=NOW, policy=BookingPolicy())
    assert [s.start.strftime("%H:%M") for s in slots] == [
        "03:30",
        "03:45",
        "04:00",
        "04:15",
    ]  # 09:00 IST


def test_booked_time_off_and_too_soon_slots_are_hidden() -> None:
    d = doctor()
    taken = datetime(2026, 10, 13, 3, 45, tzinfo=UTC)
    d.add_time_off(
        TimeOff(
            UUID(int=99),
            datetime(2026, 10, 13, 4, 15, tzinfo=UTC),
            datetime(2026, 10, 13, 5, tzinfo=UTC),
        ),
        actor=STAFF,
        at=NOW,
    )
    slots = free_slots(
        d,
        TOMORROW,
        timezone=IST,
        busy=[(taken, taken + timedelta(minutes=15))],
        now=NOW,
        policy=BookingPolicy(),
    )
    assert [s.start.strftime("%H:%M") for s in slots] == ["03:30", "04:00"]

    today = free_slots(
        d, date(2026, 10, 12), timezone=IST, busy=[], now=NOW, policy=BookingPolicy()
    )
    assert today == []  # 09:00-10:00 IST today has passed / is within the 1 h minimum notice


def test_no_slots_beyond_horizon_or_for_inactive_doctor() -> None:
    policy = BookingPolicy(horizon_days=1)
    assert (
        free_slots(doctor(), date(2026, 10, 15), timezone=IST, busy=[], now=NOW, policy=policy)
        == []
    )
    assert (
        free_slots(
            doctor(is_active=False),
            TOMORROW,
            timezone=IST,
            busy=[],
            now=NOW,
            policy=BookingPolicy(),
        )
        == []
    )


def test_requested_time_must_be_a_real_free_slot() -> None:
    off_grid = datetime(2026, 10, 13, 3, 40, tzinfo=UTC)
    with pytest.raises(SlotUnavailableError):
        require_free_slot(
            doctor(), off_grid, timezone=IST, busy=[], now=NOW, policy=BookingPolicy()
        )


def test_overlapping_working_hours_are_rejected() -> None:
    with pytest.raises(InvalidScheduleError):
        doctor().set_working_hours(
            [WorkingHours(0, time(9), time(12)), WorkingHours(0, time(11), time(13))],
            actor=STAFF,
            at=NOW,
        )


# ------------------------------------------------------------------ policy (AP-2.1, AP-4.8)
def test_policy_from_settings_and_booking_fields() -> None:
    policy = BookingPolicy.from_settings(
        {
            "approval_required": False,
            "request_expiry_hours": 2,
            "booking_fields": [
                {"key": "age", "label": "Age", "type": "number", "required": True},
                {
                    "key": "first",
                    "label": "First visit?",
                    "type": "choice",
                    "options": ["Yes", "No"],
                },
            ],
        }
    )
    assert not policy.approval_required
    assert policy.request_expiry == timedelta(hours=2)
    assert policy.clean_fields({"age": "34", "first": "yes", "junk": "x"}) == {
        "age": 34,
        "first": "Yes",
    }
    with pytest.raises(InvalidBookingFieldsError):
        policy.clean_fields({"first": "Yes"})  # age is required
    with pytest.raises(InvalidBookingFieldsError):
        policy.clean_fields({"age": "old"})


def test_reason_is_required_by_default() -> None:
    with pytest.raises(ReasonRequiredError):
        BookingPolicy().clean_reason("   ")
    assert BookingPolicy(reason_required=False).clean_reason(None) == ""


def test_patients_cannot_change_inside_the_cutoff_but_staff_can() -> None:
    appt = book(at=slot(1))  # one hour away, cut-off is 2 h
    with pytest.raises(ChangeCutoffPassedError):
        BookingPolicy().ensure_can_change(appt, PATIENT_ACTOR, NOW)
    BookingPolicy().ensure_can_change(appt, STAFF, NOW)


# ------------------------------------------------------------------ cases (§7.10)
def test_case_closes_only_without_active_appointments_and_can_reopen() -> None:
    case = Case.open(id=UUID(int=20), tenant_id=TENANT, patient_id=UUID(int=12), at=NOW)
    with pytest.raises(CaseHasActiveAppointmentsError):
        case.close(active_appointments=1, note="", actor=STAFF, at=NOW)

    case.close(active_appointments=0, note="Recovered", actor=STAFF, at=NOW)
    assert (case.is_open, case.closed_at) == (False, NOW)

    case.reopen(actor=STAFF, at=NOW + timedelta(days=3))
    assert (case.is_open, case.closed_at) == (True, None)  # RT-5: purge countdown cancelled


# ------------------------------------------------------------------ retention (§7.10)
def test_case_deletion_date_follows_rt1_rt2_and_legal_hold() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    case = Case.open(id=uuid4(), tenant_id=TenantId(uuid4()), patient_id=uuid4(), at=t0)
    days = {"closed_after": timedelta(days=60), "open_after": timedelta(days=365)}
    assert case.deletes_at(**days) == t0 + timedelta(days=365)  # RT-2
    case.close(active_appointments=0, note="", actor=Actor.system(), at=t0 + timedelta(days=5))
    assert case.deletes_at(**days) == t0 + timedelta(days=65)  # RT-1
    case.set_legal_hold(True)
    assert case.deletes_at(**days) is None  # RT-6


def test_retention_periods_come_from_the_clinic_settings() -> None:  # AP-10.7
    policy = BookingPolicy.from_settings({"retention_closed_days": 30})
    assert (policy.retention_closed, policy.retention_open) == (
        timedelta(days=30),
        timedelta(days=365),
    )


def test_deletion_request_is_decided_once_and_rejection_needs_a_reason() -> None:
    from app.modules.appointments.domain.deletion_request import DeletionRequest, DeletionStatus
    from app.modules.appointments.domain.errors import (
        DeletionRequestDecidedError,
        RejectionReasonRequiredError,
    )

    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    request = DeletionRequest.create(
        id=uuid4(), tenant_id=TenantId(uuid4()), contact_id=uuid4(), patient_ids=(uuid4(),), at=t0
    )
    assert request.answer_by == t0 + timedelta(days=7)  # AP-10.10
    with pytest.raises(RejectionReasonRequiredError):
        request.reject(reason="  ", actor=Actor.system(), at=t0)
    request.complete(counts={"patients": 1}, actor=Actor.system(), at=t0)
    assert request.status is DeletionStatus.COMPLETED
    with pytest.raises(DeletionRequestDecidedError):
        request.reject(reason="late", actor=Actor.system(), at=t0)
    assert [e.event_type for e in request.pull_events()] == [
        "DeletionRequested",
        "DeletionRequestCompleted",
    ]
