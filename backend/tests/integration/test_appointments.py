"""Appointments end to end: HTTP + use cases + real PostgreSQL (PRD §15 acceptance criteria)."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import psycopg
import pytest

from app.modules.appointments.application.commands.booking import RequestAppointmentCommand
from app.modules.appointments.application.commands.changes import RescheduleCommand
from app.modules.appointments.application.commands.decisions import EXPIRE_REQUEST_JOB
from app.modules.appointments.domain.errors import SlotUnavailableError
from app.modules.appointments.wiring import expire_stale, use_cases_for
from app.shared.application.jobs import JobContext
from app.shared.kernel.actor import Actor, Channel
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role
from tests.integration.conftest import CRON_SECRET, Api

pytestmark = pytest.mark.db
IST = ZoneInfo("Asia/Kolkata")


def tomorrow() -> date:
    return (datetime.now(IST) + timedelta(days=1)).date()


def phone() -> str:
    return "+9198" + str(uuid4().int)[:8]


@dataclass
class Clinic:
    api: Api
    tenant_id: str
    admin: dict[str, str]
    location_id: str
    doctor_id: str

    async def get(self, path: str, **params: Any) -> Any:
        response = await self.api.client.get(path, headers=self.admin, params=params)
        assert response.status_code == 200, response.text
        return response.json()

    async def post(
        self, path: str, body: dict[str, Any] | None = None, *, expect: int = 200
    ) -> Any:
        response = await self.api.client.post(path, json=body or {}, headers=self.admin)
        assert response.status_code == expect, response.text
        return response.json()

    async def slots(self, doctor_id: str | None = None) -> list[str]:
        result = await self.get(
            f"/api/doctors/{doctor_id or self.doctor_id}/slots", date=tomorrow().isoformat()
        )
        return [s["start"] for s in result["slots"]]

    async def patient(self, name: str = "Rahul Verma") -> str:
        created = await self.post(
            "/api/patients", {"phone": phone(), "full_name": name}, expect=201
        )
        return str(created["id"])

    async def add_doctor(self, name: str, user_id: str | None = None) -> str:
        doctor = await self.post(
            "/api/doctors",
            {
                "location_id": self.location_id,
                "name": name,
                "specialty": "General",
                "slot_minutes": 15,
                "user_id": user_id,
            },
            expect=201,
        )
        hours = [{"weekday": d, "start": "06:00", "end": "22:00"} for d in range(7)]
        response = await self.api.client.put(
            f"/api/doctors/{doctor['id']}/working-hours", json=hours, headers=self.admin
        )
        assert response.status_code == 200, response.text
        return str(doctor["id"])


async def open_clinic(api: Api) -> Clinic:
    root = await api.login(await api.create_super_admin())
    tenant_id = await api.create_tenant(root, "Sunrise Clinic")
    admin = await api.login(await api.add_member(tenant_id, Role.ADMIN))
    location = await api.client.post("/api/locations", json={"name": "MG Road"}, headers=admin)
    clinic = Clinic(api, tenant_id, admin, location.json()["id"], "")
    clinic.doctor_id = await clinic.add_doctor("Dr Amit")
    return clinic


async def test_book_approve_reschedule_cancel_with_full_history(api: Api) -> None:
    c = await open_clinic(api)
    patient = await c.patient()
    slots = await c.slots()
    assert len(slots) > 10

    booked = await c.post(
        "/api/appointments",
        {
            "patient_id": patient,
            "doctor_id": c.doctor_id,
            "start": slots[0],
            "reason": "Fever for 3 days",
        },
        expect=201,
    )
    assert booked["status"] == "requested"  # approval required by default (AP-2.5)
    assert booked["reference"].startswith("APT-")
    assert [a["id"] for a in await c.get("/api/appointments/requests")] == [booked["id"]]

    # Same slot for someone else: refused (AC-8, sequential case).
    other = await c.patient("Asha Rao")
    clash = await api.client.post(
        "/api/appointments",
        json={"patient_id": other, "doctor_id": c.doctor_id, "start": slots[0], "reason": "Cough"},
        headers=c.admin,
    )
    assert (clash.status_code, clash.json()["code"]) == (409, "appointments.slot_unavailable")

    assert (await c.post(f"/api/appointments/{booked['id']}/approve"))["status"] == "confirmed"

    moved = await c.post(f"/api/appointments/{booked['id']}/reschedule", {"start": slots[3]})
    assert (moved["id"], moved["reference"], moved["status"]) == (
        booked["id"],
        booked["reference"],
        "rescheduled",
    )
    assert moved["original_slot"]["start"] == booked["slot"]["start"]
    assert moved["was_rescheduled"]
    free_now = await c.slots()
    assert slots[0] in free_now  # the old time was released (AC-6)
    assert slots[3] not in free_now

    detail = await c.get(f"/api/appointments/{booked['id']}")
    assert detail["phone"].startswith("+9198")
    history = detail["history"]
    assert [h["event_type"] for h in history] == [
        "AppointmentRequested",
        "AppointmentConfirmed",
        "AppointmentRescheduled",
    ]
    assert history[2]["actor"].startswith("staff:")
    assert history[2]["data"]["old_start"] != history[2]["data"]["new_start"]

    cancelled = await c.post(
        f"/api/appointments/{booked['id']}/cancel", {"reason": "Feeling better"}
    )
    assert cancelled["status"] == "cancelled"
    assert slots[3] in await c.slots()

    [case] = await c.get(f"/api/patients/{patient}/cases")
    closed = await c.post(f"/api/cases/{case['id']}/close", {"note": "Recovered"})
    assert closed["status"] == "closed"


async def test_two_simultaneous_bookings_for_one_slot_only_one_wins(api: Api) -> None:  # AC-8
    c = await open_clinic(api)
    p1, p2 = await c.patient("A One"), await c.patient("B Two")
    start = datetime.fromisoformat((await c.slots())[5])
    tenant = TenantId(UUID(c.tenant_id))

    def attempt(patient_id: str) -> Any:
        return use_cases_for(api.container, tenant).request(
            RequestAppointmentCommand(
                tenant,
                UUID(patient_id),
                UUID(c.doctor_id),
                start,
                Actor.system(),
                Channel.WHATSAPP,
                "Checkup",
            )
        )

    results = await asyncio.gather(attempt(p1), attempt(p2), return_exceptions=True)

    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert sum(isinstance(r, SlotUnavailableError) for r in results) == 1


async def test_patient_reschedule_request_holds_new_slot_until_approved(api: Api) -> None:  # AP-4.4
    c = await open_clinic(api)
    patient = await c.patient()
    slots = await c.slots()
    booked = await c.post(
        "/api/appointments",
        {"patient_id": patient, "doctor_id": c.doctor_id, "start": slots[2], "reason": "Fever"},
        expect=201,
    )
    await c.post(f"/api/appointments/{booked['id']}/approve")

    tenant = TenantId(UUID(c.tenant_id))
    contact = Actor.contact(UUID(booked["id"]))  # any contact actor: patients go through approval
    pending = await use_cases_for(api.container, tenant).reschedule(
        RescheduleCommand(
            tenant, UUID(booked["id"]), datetime.fromisoformat(slots[8]), contact, Channel.WHATSAPP
        )
    )
    assert pending.status == "confirmed"
    assert pending.pending_slot is not None
    free = await c.slots()
    assert slots[2] not in free  # current appointment still valid
    assert slots[8] not in free  # requested time is held for this patient

    assert [a["id"] for a in await c.get("/api/appointments/requests")] == [booked["id"]]
    approved = await c.post(f"/api/appointments/{booked['id']}/reschedule/approve")
    assert approved["status"] == "rescheduled"
    assert approved["slot"]["start"] == slots[8]
    assert slots[2] in await c.slots()


async def test_doctors_only_see_their_own_appointments(api: Api) -> None:  # AP-7.2
    c = await open_clinic(api)
    doctor_email = await api.add_member(c.tenant_id, Role.DOCTOR)
    doctor_login = await api.login(doctor_email)
    doctor_user = (await api.client.get("/api/auth/me", headers=doctor_login)).json()["user_id"]
    mine = await c.add_doctor("Dr Neha", user_id=doctor_user)

    patient = await c.patient()
    own = await c.post(
        "/api/appointments",
        {
            "patient_id": patient,
            "doctor_id": mine,
            "start": (await c.slots(mine))[0],
            "reason": "Skin rash",
        },
        expect=201,
    )
    theirs = await c.post(
        "/api/appointments",
        {
            "patient_id": patient,
            "doctor_id": c.doctor_id,
            "start": (await c.slots())[0],
            "reason": "Fever",
        },
        expect=201,
    )

    listed = (await api.client.get("/api/appointments", headers=doctor_login)).json()
    assert [a["id"] for a in listed] == [own["id"]]
    other = await api.client.get(f"/api/appointments/{theirs['id']}", headers=doctor_login)
    assert other.status_code == 404
    approve = await api.client.post(f"/api/appointments/{own['id']}/approve", headers=doctor_login)
    assert approve.status_code == 403  # doctors cannot approve requests


async def test_clinic_settings_change_booking_behaviour(api: Api) -> None:
    c = await open_clinic(api)
    bad = await api.client.put(
        "/api/appointments/settings", json={"horizon_days": 0}, headers=c.admin
    )
    assert bad.status_code == 422

    put = await api.client.put(
        "/api/appointments/settings",
        json={"approval_required": False, "reason_required": False},
        headers=c.admin,
    )
    assert put.status_code == 200
    assert (await c.get("/api/appointments/settings"))["approval_required"] is False

    booked = await c.post(
        "/api/appointments",
        {"patient_id": await c.patient(), "doctor_id": c.doctor_id, "start": (await c.slots())[0]},
        expect=201,
    )
    assert booked["status"] == "confirmed"  # auto-confirmed, no reason needed


async def test_unanswered_requests_expire_and_free_the_slot(api: Api) -> None:  # AP-3.3
    c = await open_clinic(api)
    slot = (await c.slots())[1]
    booked = await c.post(
        "/api/appointments",
        {
            "patient_id": await c.patient(),
            "doctor_id": c.doctor_id,
            "start": slot,
            "reason": "Fever",
        },
        expect=201,
    )

    # The outbox delivers AppointmentRequested -> an expiry job is scheduled 4 h later.
    tick = await api.client.get(
        "/internal/jobs/tick", headers={"Authorization": f"Bearer {CRON_SECRET}"}
    )
    assert tick.status_code == 200
    dsn = os.environ["TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        row = await (
            await conn.execute(
                "SELECT run_at, payload->>'appointment_id' FROM scheduled_jobs WHERE job_type = %s "
                "AND payload->>'appointment_id' = %s",
                (EXPIRE_REQUEST_JOB, booked["id"]),
            )
        ).fetchone()
    assert row is not None
    created = datetime.fromisoformat(booked["created_at"])
    assert abs(row[0] - (created + timedelta(hours=4))) < timedelta(seconds=5)

    # When the job runs (simulated here instead of waiting 4 h):
    handler = expire_stale(api.container)
    ctx = JobContext(
        uuid4(),
        EXPIRE_REQUEST_JOB,
        TenantId(UUID(c.tenant_id)),
        {"appointment_id": booked["id"]},
        1,
    )
    await handler(ctx)
    await handler(ctx)  # idempotent

    detail = await c.get(f"/api/appointments/{booked['id']}")
    assert detail["appointment"]["status"] == "expired"
    assert detail["history"][-1]["actor"] == "system"
    assert slot in await c.slots()


async def test_history_is_append_only(api: Api) -> None:
    c = await open_clinic(api)
    await c.post(
        "/api/appointments",
        {
            "patient_id": await c.patient(),
            "doctor_id": c.doctor_id,
            "start": (await c.slots())[0],
            "reason": "Fever",
        },
        expect=201,
    )
    dsn = os.environ["TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        await conn.execute("SELECT set_config('app.tenant_id', %s, false)", (c.tenant_id,))
        assert (
            await (await conn.execute("SELECT count(*) FROM appointment_events")).fetchone()
        ) == (1,)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute("DELETE FROM appointment_events")


async def test_day_list_uses_the_clinics_local_day(api: Api) -> None:
    """00:15 IST on day D is 18:45 UTC on D-1: it must be listed under D, not D-1."""
    c = await open_clinic(api)
    night_doctor = await c.post(
        "/api/doctors",
        {
            "location_id": c.location_id,
            "name": "Dr Night",
            "specialty": "General",
            "slot_minutes": 15,
        },
        expect=201,
    )
    hours = [{"weekday": d, "start": "00:00", "end": "02:00"} for d in range(7)]
    await api.client.put(
        f"/api/doctors/{night_doctor['id']}/working-hours", json=hours, headers=c.admin
    )
    day = tomorrow()
    first = (await c.slots(night_doctor["id"]))[1]  # 00:15 IST
    booked = await c.post(
        "/api/appointments",
        {
            "patient_id": await c.patient(),
            "doctor_id": night_doctor["id"],
            "start": first,
            "reason": "Fever",
        },
        expect=201,
    )

    on_local_day = await c.get("/api/appointments", on=day.isoformat())
    on_previous_day = await c.get("/api/appointments", on=(day - timedelta(days=1)).isoformat())
    assert booked["id"] in [a["id"] for a in on_local_day]
    assert booked["id"] not in [a["id"] for a in on_previous_day]
