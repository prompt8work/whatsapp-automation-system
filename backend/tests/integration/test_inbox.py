"""Staff inbox + human handover over real webhooks and PostgreSQL (PRD §6.5, AC-9)."""

from __future__ import annotations

import pytest

from app.shared.kernel.roles import Role
from tests.integration.conftest import Api
from tests.integration.test_appointment_bot import Chat, book_tomorrow, clinic

pytestmark = pytest.mark.db


async def test_handover_loop(api: Api) -> None:
    admin, number = await clinic(api)
    chat = Chat(api, number)
    await chat.send("Hi")
    await chat.tap("Yes")
    await chat.send("Rahul Verma")
    await book_tomorrow(chat)

    [row] = (await api.client.get("/api/inbox", headers=admin)).json()
    contact_id = row["contact"]["id"]
    assert row["handover"] is None
    assert row["awaiting_reply"] is False  # the bot answered last

    # The patient asks for a person -> the chat waits for staff, and the bot goes quiet (R8).
    [ack] = await chat.send("agent")
    assert "someone from our team" in ack.lower()
    assert await chat.send("hello? is anyone there") == []

    [row] = (await api.client.get("/api/inbox", headers=admin)).json()
    assert row["handover"]["reason"] == "bot"
    assert row["handover"]["assigned_user_id"] is None
    assert row["awaiting_reply"] is True
    assert row["last_message"]["text"] == "hello? is anyone there"

    thread = (await api.client.get(f"/api/inbox/{contact_id}", headers=admin)).json()
    assert thread["can_send_text"] is True  # inside the 24 h window
    assert thread["messages"][0]["text"] == "Hi"
    assert {m["direction"] for m in thread["messages"]} == {"inbound", "outbound"}

    # Staff reply from the dashboard -> it reaches WhatsApp, and the chat is assigned to them.
    sent = await api.client.post(
        f"/api/inbox/{contact_id}/reply",
        json={"text": "Hi Rahul, Priya here. How can I help?"},
        headers=admin,
    )
    assert sent.json() == {"sent": True}
    assert chat.inbox()[-1] == "Hi Rahul, Priya here. How can I help?"
    me = (await api.client.get("/api/auth/me", headers=admin)).json()
    thread = (await api.client.get(f"/api/inbox/{contact_id}", headers=admin)).json()
    assert thread["handover"]["assigned_user_id"] == me["user_id"]

    # Hand back -> the bot answers again.
    handed = await api.client.post(f"/api/inbox/{contact_id}/handback", headers=admin)
    assert handed.status_code == 204
    [menu] = await chat.send("Hi")
    assert "Hi Rahul!" in menu


async def test_doctors_cannot_read_the_inbox(api: Api) -> None:
    root = await api.login(await api.create_super_admin())
    tenant_id = await api.create_tenant(root)
    doctor = await api.login(await api.add_member(tenant_id, Role.DOCTOR))
    assert (await api.client.get("/api/inbox", headers=doctor)).status_code == 403
