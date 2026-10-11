"""Live dashboard updates (ARCHITECTURE §8.9): commits bump per-tenant topic versions, and the
stream reports the topics that moved. The stream is read with a short window here."""

from __future__ import annotations

import pytest

from app.platform.live.application.stream import LiveStream
from app.platform.live.infrastructure.sql import SqlLiveVersions
from tests.integration.conftest import Api
from tests.integration.test_appointment_bot import Chat, book_tomorrow, clinic
from tests.integration.test_retention import tenant_of

pytestmark = pytest.mark.db


async def test_bookings_and_messages_move_their_topics(api: Api) -> None:
    admin, number = await clinic(api)
    tenant_id = await tenant_of(api, admin)
    versions = SqlLiveVersions(api.container.session_factory)
    before = await versions(tenant_id)

    chat = Chat(api, number)
    await chat.send("Hi")
    after_hi = await versions(tenant_id)
    assert after_hi["inbox"] > before.get("inbox", 0)  # message stored + replies sent
    assert after_hi.get("appointments", 0) == before.get("appointments", 0)

    await chat.tap("Yes")
    await chat.send("Rahul Verma")
    await book_tomorrow(chat)
    after_booking = await versions(tenant_id)
    assert after_booking["appointments"] > after_hi.get("appointments", 0)

    async def no_wait(_: float) -> None:
        return None

    stream = LiveStream(versions, poll=1, window=1, sleep=no_wait)
    [update] = [u async for u in stream(tenant_id, after_hi)]
    assert "appointments" in update.changed


async def test_the_stream_needs_a_signed_in_member(api: Api) -> None:
    response = await api.client.get("/api/live")
    assert response.status_code == 401
