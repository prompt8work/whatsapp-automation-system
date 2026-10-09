"""Meta Cloud API adapter against a mocked HTTP transport (no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.platform.messaging.application.ports import SendError
from app.platform.messaging.infrastructure.meta import MetaCloudGateway, render
from app.shared.kernel.messages import Buttons, Choice, ListMenu, Template, Text


def test_render_shapes() -> None:
    assert render("91987", Text("Hi"))["text"] == {"body": "Hi", "preview_url": False}

    buttons = render("91987", Buttons("Q?", (Choice("y", "Yes"),)))
    assert buttons["interactive"]["action"]["buttons"] == [
        {"type": "reply", "reply": {"id": "y", "title": "Yes"}}
    ]

    listing = render("91987", ListMenu("Q?", "Doctors", (Choice("d1", "Dr. Amit", "General"),)))
    assert listing["interactive"]["action"]["sections"][0]["rows"] == [
        {"id": "d1", "title": "Dr. Amit", "description": "General"}
    ]

    template = render("91987", Template("reminder", "en", ("Rahul",), ("confirm",)))["template"]
    assert template["language"] == {"code": "en"}
    assert template["components"][0] == {
        "type": "body",
        "parameters": [{"type": "text", "text": "Rahul"}],
    }
    assert template["components"][1]["parameters"] == [{"type": "payload", "payload": "confirm"}]


def gateway(handler: httpx.MockTransport) -> MetaCloudGateway:
    return MetaCloudGateway(httpx.AsyncClient(transport=handler), "v23.0")


async def send(gw: MetaCloudGateway) -> str:
    return await gw.send(phone_number_id="123", access_token="tok", to="91987", message=Text("Hi"))


async def test_success_returns_meta_message_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.ABC"}]})

    assert await send(gateway(httpx.MockTransport(handler))) == "wamid.ABC"
    assert seen[0].url.path == "/v23.0/123/messages"
    assert seen[0].headers["Authorization"] == "Bearer tok"
    assert json.loads(seen[0].content)["to"] == "91987"


@pytest.mark.parametrize(
    ("status", "code", "transient"),
    [(500, 1, True), (400, 130429, True), (400, 131047, False), (401, 190, False)],
)
async def test_errors_are_classified(status: int, code: int, transient: bool) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"code": code, "message": "nope"}})

    with pytest.raises(SendError) as caught:
        await send(gateway(httpx.MockTransport(handler)))
    assert caught.value.transient is transient


async def test_network_error_is_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    with pytest.raises(SendError) as caught:
        await send(gateway(httpx.MockTransport(handler)))
    assert caught.value.transient
