"""Patients chatting with the appointments bot over (simulated) WhatsApp, against PostgreSQL,
while staff act on the dashboard API. Covers PRD §7.1 greeting rules and §15 acceptance criteria.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.platform.messaging.contracts import InboundKind, InboundMessage, WebhookBatch
from app.platform.messaging.infrastructure.recording import RecordingGateway
from app.shared.kernel.messages import Buttons, ListMenu
from app.shared.kernel.roles import Role
from tests.integration.conftest import CRON_SECRET, Api, unique_phone_number_id

pytestmark = pytest.mark.db


class Chat:
    """One patient's WhatsApp, driven through the real webhook handler."""

    def __init__(self, api: Api, phone_number_id: str) -> None:
        self.api, self.phone_number_id = api, phone_number_id
        self.wa_id = "9198" + str(uuid4().int)[:8]
        gateway = api.container.whatsapp_gateway
        assert isinstance(gateway, RecordingGateway)
        self.gateway = gateway

    def _mine(self) -> list[Any]:
        return [s for s in self.gateway.sent if s.to == self.wa_id]

    async def send(self, text: str, *, choice_id: str | None = None) -> list[str]:
        before = len(self._mine())
        message = InboundMessage(
            phone_number_id=self.phone_number_id,
            wa_message_id=f"wamid.{uuid4().hex}",
            wa_id=self.wa_id,
            profile_name="Rahul",
            sent_at=datetime.now(UTC),
            kind=InboundKind.CHOICE if choice_id else InboundKind.TEXT,
            text=text,
            choice_id=choice_id,
        )
        report = await self.api.app.state.platform.conversations.handle_webhook(
            WebhookBatch(messages=[message], statuses=[])
        )
        assert report.processed == 1, vars(report)
        return [s.message.as_text() for s in self._mine()[before:]]

    async def tap(self, title_or_number: str | int) -> list[str]:
        last = self._mine()[-1].message
        assert isinstance(last, Buttons | ListMenu), last.as_text()
        if isinstance(title_or_number, int):
            choice = last.choices[title_or_number - 1]
        else:
            choice = next(c for c in last.choices if c.title.startswith(title_or_number))
        return await self.send(choice.title, choice_id=choice.id)

    def inbox(self) -> list[str]:
        return [s.message.as_text() for s in self._mine()]


async def clinic(api: Api) -> tuple[dict[str, str], str]:
    """A clinic with the appointments module, one location, one doctor (06:00-22:00 daily) and
    a connected WhatsApp number. Returns (admin headers, phone_number_id)."""
    root = await api.login(await api.create_super_admin())
    tenant_id = await api.create_tenant(root, "Sunrise Clinic")
    number = unique_phone_number_id()
    await api.client.post(
        f"/api/platform/tenants/{tenant_id}/whatsapp-numbers",
        json={"phone_number_id": number, "display_phone": "+91 1"},
        headers=root,
    )
    admin = await api.login(await api.add_member(tenant_id, Role.ADMIN))
    location = (
        await api.client.post("/api/locations", json={"name": "MG Road"}, headers=admin)
    ).json()
    doctor = (
        await api.client.post(
            "/api/doctors",
            json={
                "location_id": location["id"],
                "name": "Dr. Amit",
                "specialty": "General",
                "slot_minutes": 15,
            },
            headers=admin,
        )
    ).json()
    hours = [{"weekday": d, "start": "06:00", "end": "22:00"} for d in range(7)]
    await api.client.put(f"/api/doctors/{doctor['id']}/working-hours", json=hours, headers=admin)
    return admin, number


async def tick(api: Api) -> None:
    response = await api.client.get(
        "/internal/jobs/tick", headers={"Authorization": f"Bearer {CRON_SECRET}"}
    )
    assert response.status_code == 200


async def book_tomorrow(chat: Chat, *, time_choice: int = 1) -> str:
    """Drive a booking from the day question to the confirmation; returns the confirmation."""
    await chat.send("tomorrow")
    await chat.tap(time_choice)
    await chat.send("Fever for 3 days")
    [done] = await chat.tap("Confirm")
    return done


async def test_new_patient_books_and_staff_approval_is_sent_back(
    api: Api,
) -> None:  # R1, AC-1, AC-5
    admin, number = await clinic(api)
    chat = Chat(api, number)

    welcome, consent = await chat.send("Hi")
    assert "Welcome!" in welcome
    assert "Is that okay?" in consent
    assert await chat.tap("Yes") == ["What is the patient's full name?"]
    [day_question] = await chat.send("Rahul Verma")  # one location, one doctor: both skipped
    assert "Which day suits you?" in day_question

    done = await book_tomorrow(chat)
    assert "Request sent ✅" in done
    reference = done.split("ref ")[1].split(")")[0]

    [request] = (await api.client.get("/api/appointments/requests", headers=admin)).json()
    assert (request["reference"], request["patient_name"], request["reason"]) == (
        reference,
        "Rahul Verma",
        "Fever for 3 days",
    )

    approved = await api.client.post(f"/api/appointments/{request['id']}/approve", headers=admin)
    assert approved.status_code == 200
    await tick(api)  # outbox -> NotifyPatient -> WhatsApp
    assert f"Confirmed ✅ {reference}" in chat.inbox()[-1]


async def test_returning_patient_reschedules_and_cancels_without_repeating_details(
    api: Api,
) -> None:
    admin, number = await clinic(api)
    chat = Chat(api, number)
    await chat.send("Hi")
    await chat.tap("Yes")
    await chat.send("Rahul Verma")
    await book_tomorrow(chat)
    [request] = (await api.client.get("/api/appointments/requests", headers=admin)).json()
    await api.client.post(f"/api/appointments/{request['id']}/approve", headers=admin)

    # R2: "Hello" -> the appointment and a menu; no questions about name or doctor (AC-2).
    [menu] = await chat.send("Hello")
    assert "Hi Rahul!" in menu
    assert f"({request['reference']}) - confirmed" in menu
    assert "Reschedule" in menu
    assert "Cancel" in menu

    # Reschedule: the only appointment is picked automatically; only the new time is asked.
    [day_question] = await chat.tap("Reschedule")
    assert "Which day suits you?" in day_question
    await chat.send("tomorrow")
    await chat.tap(5)
    [requested] = await chat.tap("Confirm")
    assert "Your current time stays valid" in requested  # AP-4.4: approval mode

    queue = (await api.client.get("/api/appointments/requests", headers=admin)).json()
    assert [a["id"] for a in queue] == [request["id"]]
    await api.client.post(f"/api/appointments/{request['id']}/reschedule/approve", headers=admin)
    await tick(api)
    assert f"Your appointment {request['reference']} is now on" in chat.inbox()[-1]

    # Cancel from the menu.
    await chat.send("menu")
    await chat.tap("Cancel")
    [cancelled] = await chat.tap("Yes, cancel")
    assert f"Cancelled ✅ {request['reference']}" in cancelled
    detail = (await api.client.get(f"/api/appointments/{request['id']}", headers=admin)).json()
    assert detail["appointment"]["status"] == "cancelled"
    assert [h["event_type"] for h in detail["history"]] == [
        "AppointmentRequested",
        "AppointmentConfirmed",
        "RescheduleRequested",
        "AppointmentRescheduled",
        "AppointmentCancelled",
    ]
    assert {h["channel"] for h in detail["history"]} == {"whatsapp", "dashboard"}


async def test_family_member_is_added_under_the_same_number(api: Api) -> None:  # R3, R4, AC-3, AC-4
    admin, number = await clinic(api)
    chat = Chat(api, number)
    await chat.send("Hi")
    await chat.tap("Yes")
    await chat.send("Rahul Verma")
    await book_tomorrow(chat, time_choice=1)

    [menu] = await chat.send("Hi")
    assert "Book another" in menu
    [who] = await chat.tap("Book another")
    assert "Who is this appointment for?" in who
    assert "Rahul Verma" in who
    assert "Someone new" in who

    assert await chat.tap("Someone new") == ["What is the patient's full name?"]
    await chat.send("Asha Verma")
    done = await book_tomorrow(chat, time_choice=2)
    assert "Request sent ✅" in done

    patients = {
        a["patient_name"] for a in (await api.client.get("/api/appointments", headers=admin)).json()
    }
    assert patients == {"Rahul Verma", "Asha Verma"}


async def test_typed_answers_and_continue_after_hi(api: Api) -> None:  # R7, typed dates/times
    _, number = await clinic(api)
    chat = Chat(api, number)
    await chat.send("Hi")
    await chat.tap("Yes")
    await chat.send("Rahul Verma")
    await chat.send("tomorrow")

    [resume] = await chat.send("hi")  # greeting in the middle of the flow
    assert "Continue where we left off" in resume
    [times] = await chat.tap("Continue")
    assert "Free times on" in times

    assert await chat.send("6:15 am") == ["What is the reason for the visit? (a few words is fine)"]
    await chat.send("Checkup")
    [summary] = await chat.send("change")
    assert "Which day suits you?" in summary  # change -> back to the date (single doctor)


async def test_slot_taken_while_choosing_offers_other_times(api: Api) -> None:  # PRD §9
    admin, number = await clinic(api)
    first, second = Chat(api, number), Chat(api, number)
    for chat, name in ((first, "Rahul Verma"), (second, "Asha Rao")):
        await chat.send("Hi")
        await chat.tap("Yes")
        await chat.send(name)
        await chat.send("tomorrow")
        await chat.tap(1)
        await chat.send("Fever")
    await first.tap("Confirm")

    taken, times = await second.tap("Confirm")
    assert "someone just booked that time" in taken
    assert "Free times on" in times
    [summary] = await second.tap(1)
    assert "Please confirm" in summary
    assert "Request sent ✅" in (await second.tap("Confirm"))[0]
    assert len((await api.client.get("/api/appointments/requests", headers=admin)).json()) == 2


async def test_unknown_menu_text_and_staff_handover(api: Api) -> None:  # PL-5.3
    _, number = await clinic(api)
    chat = Chat(api, number)
    await chat.send("Hi")
    await chat.tap("Yes")
    await chat.send("Rahul Verma")
    await book_tomorrow(chat)

    await chat.send("hello")
    replies = await chat.send("what's the parking like?")
    assert replies[0] == "Please choose one of the options."
    [handover] = await chat.tap("Talk to staff")
    assert "someone from our team" in handover.lower()
