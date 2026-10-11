"""Free text the rules don't understand goes to the clinic's AI understanding - only if the
clinic switched it on (Settings -> Booking rules). A fake stands in for Claude here."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, time, timedelta

import pytest

from tests.integration.conftest import ApiFactory
from tests.integration.test_appointment_bot import Chat, clinic

pytestmark = pytest.mark.db


class FakeUnderstanding:
    def __init__(self) -> None:
        self.asked: list[str] = []

    async def date(self, text: str, today: date) -> date | None:
        self.asked.append(text)
        return today + timedelta(days=2) if "day after tomorrow" in text else None

    async def time(self, text: str) -> time | None:
        self.asked.append(text)
        return time(8, 0) if "eight in the morning" in text else None

    async def choose(self, text: str, options: Mapping[str, str]) -> str | None:
        self.asked.append(text)
        return "reschedule" if "move" in text and "reschedule" in options else None


async def test_ai_reads_free_text_only_when_the_clinic_opted_in(make_api: ApiFactory) -> None:
    fake = FakeUnderstanding()
    api = await make_api(understanding=fake)
    admin, number = await clinic(api)
    chat = Chat(api, number)
    await chat.send("Hi")
    await chat.tap("Yes")
    await chat.send("Rahul Verma")

    [not_understood, _] = await chat.send("the day after tomorrow please")
    assert "didn't get the date" in not_understood
    assert fake.asked == []  # off by default: nothing leaves the system

    rules = (await api.client.get("/api/appointments/settings", headers=admin)).json()
    await api.client.put(
        "/api/appointments/settings", json=rules | {"ai_understanding": True}, headers=admin
    )
    [times] = await chat.send("the day after tomorrow please")
    assert "Free times on" in times
    [reason] = await chat.send("around eight in the morning")
    assert "reason for the visit" in reason
    assert fake.asked == ["the day after tomorrow please", "around eight in the morning"]

    await chat.send("Fever")
    await chat.tap("Confirm")
    [request] = (await api.client.get("/api/appointments/requests", headers=admin)).json()
    await api.client.post(f"/api/appointments/{request['id']}/approve", headers=admin)
    await chat.send("Hi")
    [day_question] = await chat.send("I need to move my visit")
    assert "Which day suits you?" in day_question  # menu -> reschedule
