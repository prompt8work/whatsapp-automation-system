"""Reminders with buttons and WhatsApp templates (PRD AP-5.1, AP-5.2, PL-4.2, PL-7.2/7.3)
against PostgreSQL. The reminder job is run directly instead of waiting for its time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.modules.appointments.wiring import send_reminder
from app.platform.contacts.infrastructure.tables import contacts
from app.platform.jobs.infrastructure.tables import scheduled_jobs
from app.shared.application.jobs import JobContext
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork
from app.shared.kernel.ids import TenantId
from tests.integration.conftest import Api
from tests.integration.test_appointment_bot import Chat, clinic, tick
from tests.integration.test_retention import tenant_of

pytestmark = pytest.mark.db


async def booked(api: Api) -> tuple[dict[str, str], Chat, dict[str, Any], TenantId]:
    admin, number = await clinic(api)
    chat = Chat(api, number)
    await chat.send("Hi")
    await chat.tap("Yes")
    await chat.send("Rahul Verma")
    await chat.tap(3)  # three days ahead: both reminder times (24 h, 2 h) are in the future
    await chat.tap(1)
    await chat.send("Fever for 3 days")
    await chat.tap("Confirm")
    [appointment] = (await api.client.get("/api/appointments/requests", headers=admin)).json()
    await api.client.post(f"/api/appointments/{appointment['id']}/approve", headers=admin)
    await tick(api)
    return admin, chat, appointment, await tenant_of(api, admin)


async def reminder_jobs(api: Api, tenant_id: TenantId, appointment_id: str) -> list[Any]:
    async with SqlUnitOfWork(api.container.session_factory, None) as uow:
        rows = await uow.session.execute(
            select(scheduled_jobs.c.run_at, scheduled_jobs.c.payload).where(
                scheduled_jobs.c.job_type == "appointments.send_reminder",
                scheduled_jobs.c.tenant_id == tenant_id,
            )
        )
        return [r for r in rows if r.payload["appointment_id"] == appointment_id]


async def remind(api: Api, tenant_id: TenantId, appointment: dict[str, Any]) -> None:
    """Run the reminder job now, as the scheduler would at its time."""
    [job, *_] = await reminder_jobs(api, tenant_id, appointment["id"])
    await send_reminder(api.container)(
        JobContext(uuid4(), "appointments.send_reminder", tenant_id, job.payload, 1)
    )


async def test_confirmation_schedules_reminders_at_the_clinics_times(api: Api) -> None:
    _, _, appointment, tenant_id = await booked(api)
    start = datetime.fromisoformat(appointment["slot"]["start"])
    jobs = await reminder_jobs(api, tenant_id, appointment["id"])
    assert sorted(start - j.run_at for j in jobs) == [timedelta(hours=2), timedelta(hours=24)]


async def test_reminder_buttons_confirm_and_reschedule(api: Api) -> None:  # AP-5.1, AP-5.2
    admin, chat, appointment, tenant_id = await booked(api)
    await remind(api, tenant_id, appointment)
    reminder = chat.inbox()[-1]
    assert "⏰ Reminder: Rahul Verma with Dr. Amit" in reminder
    assert "1. Confirm\n2. Reschedule\n3. Cancel" in reminder

    [thanks] = await chat.tap("Confirm")
    assert "Thanks for confirming ✅" in thanks
    detail = (await api.client.get(f"/api/appointments/{appointment['id']}", headers=admin)).json()
    assert "AttendanceConfirmed" in [h["event_type"] for h in detail["history"]]

    # A button tapped in the middle of another conversation still goes straight to its flow.
    await chat.send("menu")
    await chat.tap("Book another")
    await remind(api, tenant_id, appointment)
    [day_question] = await chat.tap("Reschedule")
    assert "Which day suits you?" in day_question  # no "which appointment?" in between


async def test_outside_the_window_the_reminder_goes_as_the_clinics_template(api: Api) -> None:
    admin, chat, appointment, tenant_id = await booked(api)
    slots = {s["slot"]: s for s in (await api.client.get("/api/templates", headers=admin)).json()}
    assert slots["appointments.reminder"]["buttons"] == ["Confirm", "Reschedule", "Cancel"]
    bad = await api.client.put(
        "/api/templates/appointments.reminder",
        json={"template_name": "Visit Reminder!"},
        headers=admin,
    )
    assert bad.status_code == 422
    mapped = await api.client.put(
        "/api/templates/appointments.reminder",
        json={"template_name": "visit_reminder", "language": "en"},
        headers=admin,
    )
    assert mapped.status_code == 204

    async with SqlUnitOfWork(api.container.session_factory, tenant_id) as uow:  # 2 days quiet
        await uow.session.execute(
            update(contacts).values(last_inbound_at=datetime.now(UTC) - timedelta(days=2))
        )
        await uow.commit()
    await remind(api, tenant_id, appointment)
    sent = chat.gateway.sent[-1].message
    assert sent.as_text().startswith("[template visit_reminder] Rahul Verma | Dr. Amit")
    assert sent.button_payloads == (  # type: ignore[union-attr]
        f"rem:confirm:{appointment['id']}",
        f"rem:reschedule:{appointment['id']}",
        f"rem:cancel:{appointment['id']}",
    )
    # The template's quick-reply button comes back as the same payload (AP-5.2).
    [cancel_question] = await chat.send("Cancel", choice_id=f"rem:cancel:{appointment['id']}")
    assert "Cancel this appointment?" in cancel_question


async def test_stop_turns_reminders_off_and_moved_appointments_skip_old_ones(api: Api) -> None:
    _, chat, appointment, tenant_id = await booked(api)
    [old_job, *_] = await reminder_jobs(api, tenant_id, appointment["id"])
    await chat.send("STOP")
    before = len(chat.inbox())
    await remind(api, tenant_id, appointment)
    assert len(chat.inbox()) == before  # PL-2.4: opted out

    await chat.send("START")
    stale = dict(old_job.payload) | {"start": "2020-01-01T00:00:00+00:00"}
    before = len(chat.inbox())
    await send_reminder(api.container)(
        JobContext(uuid4(), "appointments.send_reminder", tenant_id, stale, 1)
    )
    assert len(chat.inbox()) == before  # the appointment is no longer at that time
