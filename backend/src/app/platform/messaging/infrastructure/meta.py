"""Meta WhatsApp Cloud API: render OutboundMessage -> JSON and POST it.

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/messages
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.platform.messaging.application.ports import SendError
from app.shared.kernel.messages import (
    Buttons,
    LinkButton,
    ListMenu,
    OrderDetails,
    OutboundMessage,
    Template,
    Text,
)

log = structlog.get_logger(__name__)
GRAPH_URL = "https://graph.facebook.com"
# Meta error codes that are worth retrying (rate limits, temporary errors).
_TRANSIENT_CODES = {1, 2, 4, 80007, 130429, 131000, 131016, 133004}


def render(to: str, message: OutboundMessage) -> dict[str, Any]:
    base: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
    }
    match message:
        case Text(body=body):
            return base | {"type": "text", "text": {"body": body, "preview_url": False}}
        case Buttons(body=body, choices=choices):
            buttons = [{"type": "reply", "reply": {"id": c.id, "title": c.title}} for c in choices]
            return base | {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body},
                    "action": {"buttons": buttons},
                },
            }
        case ListMenu(body=body, button=button, choices=choices):
            rows = [
                {"id": c.id, "title": c.title}
                | ({"description": c.description} if c.description else {})
                for c in choices
            ]
            return base | {
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": body},
                    "action": {"button": button, "sections": [{"title": button, "rows": rows}]},
                },
            }
        case Template(name=name, language=language, body_params=params, button_payloads=payloads):
            components: list[dict[str, Any]] = []
            if params:
                components.append(
                    {"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}
                )
            for index, payload in enumerate(payloads):
                components.append(
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": str(index),
                        "parameters": [{"type": "payload", "payload": payload}],
                    }
                )
            return base | {
                "type": "template",
                "template": {
                    "name": name,
                    "language": {"code": language},
                    "components": components,
                },
            }
        case LinkButton(body=body, title=title, url=url):
            return base | {
                "type": "interactive",
                "interactive": {
                    "type": "cta_url",
                    "body": {"text": body},
                    "action": {
                        "name": "cta_url",
                        "parameters": {"display_text": title, "url": url},
                    },
                },
            }
        case OrderDetails() as order:
            amount = {"value": order.amount_minor, "offset": 100}
            return base | {
                "type": "interactive",
                "interactive": {
                    "type": "order_details",
                    "body": {"text": order.body},
                    "action": {
                        "name": "review_and_pay",
                        "parameters": {
                            "reference_id": order.reference_id,
                            "type": "digital-goods",
                            "payment_type": "upi",
                            "payment_configuration": order.configuration,
                            "currency": order.currency,
                            "total_amount": amount,
                            "order": {
                                "status": "pending",
                                "items": [
                                    {
                                        "retailer_id": order.reference_id,
                                        "name": order.item_name,
                                        "amount": amount,
                                        "quantity": 1,
                                    }
                                ],
                                "subtotal": amount,
                            },
                        },
                    },
                },
            }
    raise TypeError(f"Unsupported message {message!r}")


class MetaCloudGateway:
    def __init__(self, client: httpx.AsyncClient, api_version: str) -> None:
        self._client, self._api_version = client, api_version

    async def send(
        self, *, phone_number_id: str, access_token: str, to: str, message: OutboundMessage
    ) -> str:
        url = f"{GRAPH_URL}/{self._api_version}/{phone_number_id}/messages"
        try:
            response = await self._client.post(
                url,
                json=render(to, message),
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise SendError(f"Network error: {type(exc).__name__}", transient=True) from exc

        if response.is_success:
            return str(response.json()["messages"][0]["id"])

        error = _error(response)
        code = error.get("code")
        transient = response.status_code >= 500 or code in _TRANSIENT_CODES
        log.warning("whatsapp.send_failed", status=response.status_code, code=code)
        raise SendError(
            f"Meta {response.status_code} code={code}: {error.get('message', '')}"[:300],
            transient=transient,
            code=str(code) if code is not None else None,
        )


def _error(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    error = body.get("error") if isinstance(body, dict) else None
    return error if isinstance(error, dict) else {}
