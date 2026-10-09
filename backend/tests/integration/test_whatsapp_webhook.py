"""A whole WhatsApp conversation through signed Meta webhooks + real PostgreSQL.

Uses a tiny test-only module ("echo": consent -> "your name?" -> "Hello <name>") so the test
exercises the platform, not a feature module.
"""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID

import psycopg
import pytest
from pydantic import SecretStr

from app.platform.conversations.contracts import consent_step
from app.platform.messaging.infrastructure.recording import RecordingGateway
from app.platform.messaging.integration import sign
from app.shared.application.conversation import (
    BaseStep,
    Finish,
    Flow,
    FlowContext,
    InboundReply,
    StepResult,
)
from app.shared.module import ModuleDefinition
from tests.integration.conftest import Api, ApiFactory, unique, unique_phone_number_id

pytestmark = pytest.mark.db
APP_SECRET = "test-meta-app-secret"
VERIFY_TOKEN = "test-verify-token"


class AskName(BaseStep):
    key = "name"

    async def prompt(self, ctx: FlowContext) -> None:
        ctx.say("Your name?")

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        ctx.say(f"Hello {reply.text}")
        return Finish()


class HiRule:
    module_key = "echo"
    priority = 1

    async def flow_for(self, ctx: FlowContext) -> str | None:
        return "echo.hello" if ctx.reply.normalized == "hi" else None


ECHO = ModuleDefinition(
    key="echo",
    flows=[lambda s: Flow("echo.hello", "echo", (consent_step(s), AskName()))],
    router_rules=[lambda _s: HiRule()],
)


def webhook(
    phone_number_id: str,
    wamid: str,
    *,
    text: str | None = None,
    choice: tuple[str, str] | None = None,
    statuses: list[dict[str, Any]] | None = None,
) -> bytes:
    messages = []
    if text is not None:
        messages.append(
            {
                "from": "919811122233",
                "id": wamid,
                "timestamp": "1760000000",
                "type": "text",
                "text": {"body": text},
            }
        )
    if choice is not None:
        messages.append(
            {
                "from": "919811122233",
                "id": wamid,
                "timestamp": "1760000000",
                "type": "interactive",
                "interactive": {
                    "type": "button_reply",
                    "button_reply": {"id": choice[0], "title": choice[1]},
                },
            }
        )
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550001111", "phone_number_id": phone_number_id},
        "contacts": [{"profile": {"name": "Rahul"}, "wa_id": "919811122233"}],
        "messages": messages,
        "statuses": statuses or [],
    }
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": value}]}],
    }
    return json.dumps(payload).encode()


async def post(api: Api, body: bytes, *, secret: str = APP_SECRET) -> dict[str, int]:
    response = await api.client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": sign(secret, body), "Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text
    result: dict[str, int] = response.json()
    return result


async def setup(make_api: ApiFactory) -> tuple[Api, str, str]:
    api = await make_api(
        modules=[ECHO],
        meta_app_secret=SecretStr(APP_SECRET),
        meta_verify_token=SecretStr(VERIFY_TOKEN),
    )
    root = await api.login(await api.create_super_admin())
    created = await api.client.post(
        "/api/platform/tenants",
        json={"name": "Echo Clinic", "slug": unique("echo"), "modules": ["echo"]},
        headers=root,
    )
    tenant_id = created.json()["id"]
    number = unique_phone_number_id()
    await api.client.post(
        f"/api/platform/tenants/{tenant_id}/whatsapp-numbers",
        json={"phone_number_id": number, "display_phone": "+91 1"},
        headers=root,
    )
    return api, tenant_id, number


def sent_texts(api: Api, since: int) -> list[str]:
    gateway = api.container.whatsapp_gateway
    assert isinstance(gateway, RecordingGateway)
    return [s.message.as_text() for s in gateway.sent[since:]]


async def test_conversation_over_webhooks(make_api: ApiFactory) -> None:
    api, tenant_id, number = await setup(make_api)
    gateway = api.container.whatsapp_gateway
    assert isinstance(gateway, RecordingGateway)
    start = len(gateway.sent)

    assert (await post(api, webhook(number, unique("wamid.in.1"), text="hi")))["processed"] == 1
    assert "Is that okay?" in sent_texts(api, start)[0]

    await post(api, webhook(number, unique("wamid.in.2"), choice=("consent:yes", "Yes, continue")))
    assert sent_texts(api, start)[1] == "Your name?"

    name_message = webhook(number, unique("wamid.in.3"), text="Rahul")
    await post(api, name_message)
    assert sent_texts(api, start)[2] == "Hello Rahul"

    # Meta retries the same delivery: recognised, nothing is sent twice (PRD AC-11).
    retry = await post(api, name_message)
    assert retry["duplicates"] == 1
    assert len(sent_texts(api, start)) == 3

    # Delivery receipt for our first reply.
    first_out = gateway.sent[start]
    receipt_id = first_out.wa_message_id
    status = webhook(
        number,
        unique("wamid.none"),
        statuses=[{"id": receipt_id, "status": "read", "timestamp": "1760000001"}],
    )
    assert (await post(api, status))["statuses"] == 1
    assert first_out.to == "919811122233"

    # What the database now holds (as the tenant, through RLS).
    dsn = os.environ["TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        await conn.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant_id,))
        rows = await (
            await conn.execute(
                "SELECT direction, status FROM messages ORDER BY created_at, direction"
            )
        ).fetchall()
        consent = await (
            await conn.execute("SELECT consent_given_at IS NOT NULL FROM contacts")
        ).fetchone()
        session = await (
            await conn.execute("SELECT flow_key, last_flow_key FROM conversation_sessions")
        ).fetchone()
        safety = await (
            await conn.execute(
                "SELECT count(*) FROM scheduled_jobs WHERE tenant_id = %s AND status = 'pending'",
                (UUID(tenant_id),),
            )
        ).fetchone()

    assert sorted(rows) == sorted(
        [("inbound", "processed")] * 3
        + [("outbound", "read"), ("outbound", "sent"), ("outbound", "sent")]
    )
    assert consent == (True,)
    assert session == (None, "echo.hello")  # flow finished
    assert safety == (0,)  # every safety-net job was cancelled after processing


async def test_signature_and_subscription_checks(make_api: ApiFactory) -> None:
    api, _, number = await setup(make_api)
    body = webhook(number, unique("wamid.sig"), text="hi")

    forged = await api.client.post(
        "/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sign("wrong", body)}
    )
    assert forged.status_code == 401

    ok = await api.client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "12345",
        },
    )
    assert (ok.status_code, ok.text) == (200, "12345")
    bad = await api.client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"},
    )
    assert bad.status_code == 403


async def test_messages_to_numbers_we_do_not_know_are_ignored(make_api: ApiFactory) -> None:
    api, _, _ = await setup(make_api)
    result = await post(api, webhook("999999999999999", unique("wamid.unknown"), text="hi"))
    assert result["unknown_number"] == 1
