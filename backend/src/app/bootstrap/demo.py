"""`cli seed-demo`: a demo clinic full of realistic activity, to see the system as it looks in use.

Everything goes through the real code paths - patients book through the WhatsApp bot (simulated:
WHATSAPP_SENDER=recording, nothing leaves the machine), staff act through the dashboard API,
background jobs run as the cron tick would. Past activity is created by running the same app
with its clock set back, so history, payments and retention dates are all consistent.

What you get (clinic "Sunrise Clinic (Demo)", logins printed at the end):
- 2 locations, 3 doctors with hours; booking rules with a ₹500 fee; payment methods; templates
- past visits: completed, a no-show, paid / refunded payments, a closed case deleted in 3 days
- today onwards: confirmed appointments (paid and unpaid), new requests, a reschedule request,
  a cancellation, a declined request
- inbox: a patient waiting for staff, a chat staff took over and answered
- privacy: a "delete my data" request waiting for a decision
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy import delete, text

from app.bootstrap.platform import Platform, build_platform
from app.bootstrap.settings import Settings
from app.main import create_app
from app.platform.identity.application.commands.members import AddMemberCommand
from app.platform.jobs.application.dispatch_outbox import DispatchOutbox
from app.platform.jobs.application.run_due_jobs import RunDueJobs
from app.platform.jobs.infrastructure.unit_of_work import SqlJobsUnitOfWork
from app.platform.messaging.contracts import InboundKind, InboundMessage, WebhookBatch
from app.platform.messaging.infrastructure.recording import RecordingGateway
from app.platform.tenancy.application.commands.connect_whatsapp_number import (
    ConnectWhatsAppNumber,
    ConnectWhatsAppNumberCommand,
)
from app.platform.tenancy.application.commands.tenants import CreateTenant, CreateTenantCommand
from app.platform.tenancy.application.queries.tenants import ListTenants
from app.platform.tenancy.infrastructure.tables import tenants
from app.platform.tenancy.infrastructure.unit_of_work import SqlTenancyUnitOfWork
from app.shared.application.auth import Principal
from app.shared.application.jobs import ScheduleJob
from app.shared.infrastructure.db import create_engine
from app.shared.infrastructure.tables import metadata
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import SystemClock
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import Buttons, ListMenu
from app.shared.kernel.roles import Role

SLUG = "sunrise-demo"
NUMBER_ID = "100000000000777"
DOMAIN = "sunrise.demo"


class NoJobs:
    """Job scheduler for the time-shifted copies of the app: their jobs would be due at once
    in real time, so a running `cli tick` loop (or the prod scheduler) would grab them mid-seed -
    e.g. process a chat message twice. The seeder finishes everything itself, so it needs none."""

    async def schedule(self, job: ScheduleJob) -> None:
        return None

    async def cancel(self, idempotency_key: str) -> None:
        return None


class ShiftedClock:
    """The real clock, moved back by `days` - time still passes while the seeder runs."""

    def __init__(self, days: float) -> None:
        self._shift = timedelta(days=days)

    def now(self) -> datetime:
        return datetime.now(UTC) - self._shift


@dataclass
class Clinic:
    """One running copy of the app at some point in time, signed in as the clinic admin."""

    platform: Platform
    app: FastAPI
    client: httpx.AsyncClient
    headers: dict[str, str] = field(default_factory=dict)

    async def call(self, method: str, url: str, json: Any = None) -> Any:
        response = await self.client.request(method, url, json=json, headers=self.headers)
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {url} -> {response.status_code}: {response.text}")
        return response.json() if response.content else None

    async def tick(self) -> None:
        """Deliver events and run due jobs, as the production scheduler does every minute."""
        c = self.platform.container
        uow = SqlJobsUnitOfWork(c.session_factory)
        for _ in range(3):  # handlers may create more events / jobs
            await DispatchOutbox(uow, c.event_handlers, c.clock)()
            await RunDueJobs(uow, c.job_handlers, c.clock)()

    async def close(self) -> None:
        await self.client.aclose()
        await self.platform.container.engine.dispose()
        await self.platform.container.purge_engine.dispose()


async def _open(settings: Settings, days_ago: float = 0) -> Clinic:
    if days_ago:
        platform = build_platform(settings, clock=ShiftedClock(days_ago), jobs=NoJobs())
    else:
        platform = build_platform(settings, clock=SystemClock())
    app = create_app(settings, platform=platform)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://demo")
    return Clinic(platform, app, client)


def _act_as_admin(clinic: Clinic, admin_id: UUID, tenant_id: TenantId) -> None:
    """A short-lived admin token, issued directly: the seeder never needs anyone's password
    (demo logins created earlier keep the password their owner chose)."""
    c = clinic.platform.container
    principal = Principal(
        user_id=admin_id,
        tenant_id=tenant_id,
        role=Role.ADMIN,
        permissions=c.permissions.for_role(Role.ADMIN),
    )
    clinic.headers = {"Authorization": f"Bearer {c.access_tokens.issue(principal).token}"}


class Patient:
    """A WhatsApp user chatting with the bot (simulated, nothing is sent anywhere)."""

    def __init__(self, wa_id: str, profile: str) -> None:
        self.wa_id, self.profile = wa_id, profile

    def _last(self, clinic: Clinic) -> Any:
        gateway = clinic.platform.container.whatsapp_gateway
        assert isinstance(gateway, RecordingGateway)
        mine = [s.message for s in gateway.sent if s.to.lstrip("+") == self.wa_id]
        return mine[-1] if mine else None

    async def say(self, clinic: Clinic, text: str, choice_id: str | None = None) -> str:
        message = InboundMessage(
            phone_number_id=NUMBER_ID,
            wa_message_id=f"wamid.demo.{uuid4().hex}",
            wa_id=self.wa_id,
            profile_name=self.profile,
            sent_at=clinic.platform.container.clock.now(),
            kind=InboundKind.CHOICE if choice_id else InboundKind.TEXT,
            text=text,
            choice_id=choice_id,
        )
        await clinic.platform.conversations.handle_webhook(
            WebhookBatch(messages=[message], statuses=[])
        )
        last = self._last(clinic)
        return last.as_text() if last else ""

    async def tap(self, clinic: Clinic, title: str | int) -> str:
        last = self._last(clinic)
        assert isinstance(last, Buttons | ListMenu), f"no buttons to tap: {last}"
        if isinstance(title, int):
            choice = last.choices[min(title, len(last.choices) - 1)]
        else:
            choice = next(c for c in last.choices if c.title.startswith(title))
        return await self.say(clinic, choice.title, choice.id)

    async def book(
        self,
        clinic: Clinic,
        *,
        name: str,
        reason: str,
        location: str = "MG Road",
        doctor: str = "Dr. Anjali Mehta",
        day: int = 0,
        time: int = 2,
    ) -> None:
        """Answer whatever the bot asks until the booking is done (order-independent)."""
        text = await self.say(clinic, "Hi")
        for _ in range(20):
            if "Request sent" in text or "Booked ✅" in text:
                return
            if "Is that okay" in text:
                text = await self.tap(clinic, "Yes")
            elif "Hi " in text and "Book" in text:  # returning: menu
                text = await self.tap(clinic, "Book")
            elif "Who is this appointment for" in text:
                last = self._last(clinic)
                titles = [c.title for c in last.choices]
                text = await self.tap(clinic, name[:24] if name[:24] in titles else "Someone new")
            elif "full name" in text:
                text = await self.say(clinic, name)
            elif "Which of our clinics" in text:
                text = await self.tap(clinic, location)
            elif "Which doctor" in text:
                text = await self.tap(clinic, doctor[:24])
            elif "Which day suits you" in text:
                text = await self.tap(clinic, day)
            elif "Free times on" in text:
                text = await self.tap(clinic, time)
            elif "just booked that time" in text:
                time += 1
                text = await self.tap(clinic, time)
            elif "reason for the visit" in text:
                text = await self.say(clinic, reason)
            elif "Please confirm" in text:
                text = await self.tap(clinic, "Confirm")
            else:
                raise RuntimeError(f"Unexpected bot message for {name}: {text}")
        raise RuntimeError(f"Booking for {name} did not finish; the bot last said: {text}")


async def _latest_request(clinic: Clinic, patient_name: str) -> dict[str, Any]:
    queue = await clinic.call("GET", "/api/appointments/requests")
    return next(a for a in queue if a["patient_name"] == patient_name and not a["pending_slot"])


async def reset_demo(settings: Settings, tenant_id: TenantId) -> None:
    """Delete the demo clinic and everything it owns (only that tenant), as the schema owner:
    the API role may not delete history or payments, on purpose. Demo user accounts are kept
    (they are reused on the next seed)."""
    engine = create_engine(settings.database_migration_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
            )
            for table in reversed(metadata.sorted_tables):  # children before parents
                if "tenant_id" in table.c:
                    await conn.execute(delete(table).where(table.c.tenant_id == tenant_id))
            await conn.execute(delete(tenants).where(tenants.c.id == tenant_id))
    finally:
        await engine.dispose()


async def seed_demo(settings: Settings, password: str, *, reset: bool = False) -> str:
    if settings.whatsapp_sender != "recording":
        sys.exit("seed-demo needs WHATSAPP_SENDER=recording - it must never message real people")
    now = await _open(settings)
    try:
        tenancy = SqlTenancyUnitOfWork(now.platform.container.session_factory, None)
        existing = next((t for t in await ListTenants(tenancy)() if t.slug == SLUG), None)
        if existing is not None:
            if not reset:
                sys.exit(
                    f"The demo clinic ({SLUG}) already exists. "
                    "Run `seed-demo --reset` to delete it and create it again."
                )
            await reset_demo(settings, TenantId(existing.id))
        return await _seed(settings, now, password)
    finally:
        await now.close()


async def _seed(settings: Settings, now: Clinic, password: str) -> str:
    c, system = now.platform.container, Actor.system()
    tenancy = SqlTenancyUnitOfWork(c.session_factory, None)

    # ---------------------------------------------------------------- clinic, people, setup
    tenant = await CreateTenant(tenancy, c.clock, c.ids)(
        CreateTenantCommand(
            "Sunrise Clinic (Demo)",
            SLUG,
            system,
            timezone="Asia/Kolkata",
            modules=("appointments",),
        )
    )
    tenant_id = TenantId(tenant.id)
    await ConnectWhatsAppNumber(tenancy, c.clock, c.ids)(
        ConnectWhatsAppNumberCommand(tenant_id, NUMBER_ID, "+91 80 4000 7777", system)
    )
    users = {
        "admin": ("Priya Nair", Role.ADMIN),
        "reception": ("Kiran Shetty", Role.STAFF),
        "dr.mehta": ("Dr. Anjali Mehta", Role.DOCTOR),
    }
    members = {}
    for local, (full_name, role) in users.items():
        members[local] = await now.platform.identity.add_member(
            AddMemberCommand(tenant_id, f"{local}@{DOMAIN}", full_name, role, system, password)
        )
    admin_id = members["admin"].user_id
    _act_as_admin(now, admin_id, tenant_id)

    mg = await now.call("POST", "/api/locations", {"name": "MG Road"})
    indira = await now.call("POST", "/api/locations", {"name": "Indiranagar"})
    doctors = [
        (mg, "Dr. Anjali Mehta", "General Physician", 15, members["dr.mehta"].user_id),
        (mg, "Dr. Rohan Iyer", "Paediatrics", 20, None),
        (indira, "Dr. Kavita Rao", "Dermatology", 30, None),
    ]
    for location, name, specialty, minutes, user_id in doctors:
        doctor = await now.call(
            "POST",
            "/api/doctors",
            {
                "location_id": location["id"],
                "name": name,
                "specialty": specialty,
                "slot_minutes": minutes,
                "user_id": str(user_id) if user_id else None,
            },
        )
        hours = [{"weekday": d, "start": "07:00", "end": "21:00"} for d in range(7)]
        await now.call("PUT", f"/api/doctors/{doctor['id']}/working-hours", hours)

    rules = await now.call("GET", "/api/appointments/settings")
    await now.call("PUT", "/api/appointments/settings", rules | {"consultation_fee": 500})
    await now.call(
        "PUT",
        "/api/payments/settings",
        {"methods": ["whatsapp_pay", "at_clinic"], "whatsapp_pay_configuration": "sunrise-upi"},
    )
    for slot, template in (
        ("appointments.reminder", "visit_reminder"),
        ("appointments.update", "appointment_update"),
    ):
        await now.call(
            "PUT", f"/api/templates/{slot}", {"template_name": template, "language": "en"}
        )

    # ---------------------------------------------------------------- ~2 months ago: closed case
    old = await _open(settings, days_ago=62)
    try:
        _act_as_admin(old, admin_id, tenant_id)
        meera = Patient("919845000101", "Meera")
        await meera.book(old, name="Meera Krishnan", reason="Persistent cough", day=0, time=3)
        visit = await _latest_request(old, "Meera Krishnan")
        await old.call("POST", f"/api/appointments/{visit['id']}/approve")
        await old.tick()
    finally:
        await old.close()
    later = await _open(settings, days_ago=57)  # visit done, paid, case closed 57 days ago
    try:
        _act_as_admin(later, admin_id, tenant_id)
        await later.call("POST", f"/api/appointments/{visit['id']}/attendance", {"attended": True})
        [payment] = await later.call("GET", f"/api/payments?subject_id={visit['id']}")
        await later.call("POST", f"/api/payments/{payment['id']}/mark-paid", {"note": "UPI"})
        await later.call(
            "POST", f"/api/cases/{visit['case_id']}/close", {"note": "Recovered fully"}
        )
        await later.tick()
    finally:
        await later.close()

    # ---------------------------------------------------------------- last week: past visits
    week = await _open(settings, days_ago=8)
    past: dict[str, dict[str, Any]] = {}
    try:
        _act_as_admin(week, admin_id, tenant_id)
        bookings = [
            (
                "919845000201",
                "Rahul Verma",
                "Fever and body ache",
                "MG Road",
                "Dr. Anjali Mehta",
                1,
                1,
            ),
            ("919845000202", "Anita Desai", "Skin rash", "Indiranagar", "Dr. Kavita Rao", 2, 2),
            ("919845000203", "Arjun Menon", "Vaccination", "MG Road", "Dr. Rohan Iyer", 3, 3),
            (
                "919845000204",
                "Fatima Sheikh",
                "Follow-up visit",
                "MG Road",
                "Dr. Anjali Mehta",
                4,
                4,
            ),
            ("919845000205", "Suresh Pillai", "Back pain", "MG Road", "Dr. Anjali Mehta", 5, 5),
        ]
        for wa_id, name, reason, location, doctor, day, time in bookings:
            await Patient(wa_id, name.split()[0]).book(
                week, name=name, reason=reason, location=location, doctor=doctor, day=day, time=time
            )
            past[name] = await _latest_request(week, name)
            await week.call("POST", f"/api/appointments/{past[name]['id']}/approve")
        await week.tick()
    finally:
        await week.close()

    for name in ("Rahul Verma", "Anita Desai", "Arjun Menon", "Fatima Sheikh"):
        await now.call(
            "POST", f"/api/appointments/{past[name]['id']}/attendance", {"attended": True}
        )
    await now.call(
        "POST", f"/api/appointments/{past['Suresh Pillai']['id']}/attendance", {"attended": False}
    )
    for name, note in (
        ("Rahul Verma", "cash"),
        ("Anita Desai", "UPI at counter"),
        ("Arjun Menon", "cash"),
    ):
        [payment] = await now.call("GET", f"/api/payments?subject_id={past[name]['id']}")
        await now.call("POST", f"/api/payments/{payment['id']}/mark-paid", {"note": note})
    [refund] = await now.call("GET", f"/api/payments?subject_id={past['Arjun Menon']['id']}")
    await now.call(
        "POST", f"/api/payments/{refund['id']}/mark-refunded", {"note": "Vaccine out of stock"}
    )
    await now.tick()

    # ---------------------------------------------------------------- today onwards
    upcoming = [
        ("919845000301", "Asha Rao", "Migraine", "MG Road", "Dr. Anjali Mehta", 0, 2, "confirm"),
        (
            "919845000302",
            "Vikram Joshi",
            "Annual check-up",
            "MG Road",
            "Dr. Anjali Mehta",
            1,
            4,
            "confirm",
        ),
        ("919845000303", "Diya Joshi", "Ear pain", "MG Road", "Dr. Rohan Iyer", 1, 2, "confirm"),
        (
            "919845000304",
            "Neha Kapoor",
            "Acne treatment",
            "Indiranagar",
            "Dr. Kavita Rao",
            2,
            3,
            "confirm",
        ),
        (
            "919845000305",
            "Imran Khan",
            "Sore throat",
            "MG Road",
            "Dr. Anjali Mehta",
            2,
            6,
            "decline",
        ),
        (
            "919845000306",
            "Lakshmi Iyer",
            "Knee pain",
            "MG Road",
            "Dr. Anjali Mehta",
            3,
            1,
            "pending",
        ),
        (
            "919845000307",
            "Karan Malhotra",
            "Allergy",
            "Indiranagar",
            "Dr. Kavita Rao",
            3,
            5,
            "pending",
        ),
        (
            "919845000308",
            "Pooja Hegde",
            "Child fever",
            "MG Road",
            "Dr. Rohan Iyer",
            4,
            2,
            "pending",
        ),
        (
            "919845000309",
            "Sanjay Gupta",
            "Diabetes review",
            "MG Road",
            "Dr. Anjali Mehta",
            5,
            3,
            "confirm",
        ),
    ]
    patients: dict[str, Patient] = {}
    current: dict[str, dict[str, Any]] = {}
    for wa_id, name, reason, location, doctor, day, time, outcome in upcoming:
        patients[name] = Patient(wa_id, name.split()[0])
        await patients[name].book(
            now, name=name, reason=reason, location=location, doctor=doctor, day=day, time=time
        )
        current[name] = await _latest_request(now, name)
        if outcome == "confirm":
            await now.call("POST", f"/api/appointments/{current[name]['id']}/approve")
        elif outcome == "decline":
            await now.call(
                "POST",
                f"/api/appointments/{current[name]['id']}/decline",
                {"reason": "Dr. Mehta is fully booked that evening - please pick another time."},
            )
    await now.tick()

    # Vikram paid in the chat; Sanjay cancels; Neha asks to move her appointment.
    [vikram_pay] = await now.call(
        "GET", f"/api/payments?subject_id={current['Vikram Joshi']['id']}"
    )
    await now.call("POST", f"/api/payments/{vikram_pay['id']}/mark-paid", {"note": "paid online"})
    sanjay = patients["Sanjay Gupta"]
    await sanjay.say(now, "menu")
    await sanjay.tap(now, "Cancel")
    await sanjay.tap(now, "Yes, cancel")
    neha = patients["Neha Kapoor"]
    await neha.say(now, "menu")
    await neha.tap(now, "Reschedule")
    await neha.tap(now, 4)
    await neha.tap(now, 1)
    await neha.tap(now, "Confirm")

    # Inbox: one patient waiting for staff, one chat staff took over and answered.
    asha = patients["Asha Rao"]
    await asha.say(now, "agent")
    await asha.say(now, "Can I bring my previous reports along? They are from another hospital.")
    question = Patient("919845000401", "Ramesh")
    await question.say(now, "Hello")
    await question.tap(now, "Yes")
    await question.say(now, "agent")
    await question.say(now, "Do you accept Star Health insurance cards?")
    inbox = await now.call("GET", "/api/inbox")
    ramesh = next(row["contact"] for row in inbox if row["contact"]["profile_name"] == "Ramesh")
    await now.call("POST", f"/api/inbox/{ramesh['id']}/takeover")
    await now.call(
        "POST",
        f"/api/inbox/{ramesh['id']}/reply",
        {
            "text": "Hi Ramesh! Yes, we accept Star Health cashless cards. "
            "Please bring the card and an ID."
        },
    )

    # Privacy: Suresh (the no-show) asks to delete his data.
    suresh = Patient("919845000205", "Suresh")
    await suresh.say(now, "DELETE MY DATA")
    await suresh.tap(now, "Yes, delete")
    await now.tick()

    return (
        "Demo clinic ready: Sunrise Clinic (Demo)\n"
        f"  admin       admin@{DOMAIN}\n"
        f"  reception   reception@{DOMAIN}   (staff)\n"
        f"  doctor      dr.mehta@{DOMAIN}    (sees only Dr. Mehta's appointments)\n"
        "  password    the one you just entered\n"
        f"Chat as a patient: uv run python -m app.bootstrap.cli simulate --tenant {SLUG}"
    )
