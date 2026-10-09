"""Parsing Meta webhook payloads (shapes from Meta's payload examples)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.platform.messaging.domain.inbound import DeliveryStatus, InboundKind
from app.platform.messaging.infrastructure.webhook import parse_webhook, sign, verify_signature

PHONE_NUMBER_ID = "106540352242922"


def payload(
    messages: Sequence[dict[str, Any]] = (), statuses: Sequence[dict[str, Any]] = ()
) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550001111",
                                "phone_number_id": PHONE_NUMBER_ID,
                            },
                            "contacts": [{"profile": {"name": "Rahul"}, "wa_id": "919876543210"}],
                            "messages": list(messages),
                            "statuses": list(statuses),
                        },
                    }
                ],
            }
        ],
    }


def msg(type_: str, **body: Any) -> dict[str, Any]:
    return {
        "from": "919876543210",
        "id": f"wamid.{type_}",
        "timestamp": "1760000000",
        "type": type_,
        **body,
    }


def test_text_message() -> None:
    [m] = parse_webhook(payload([msg("text", text={"body": "  Hi there "})])).messages
    assert (m.kind, m.text, m.profile_name, m.phone_number_id) == (
        InboundKind.TEXT,
        "Hi there",
        "Rahul",
        PHONE_NUMBER_ID,
    )


def test_button_list_and_template_replies_become_choices() -> None:
    batch = parse_webhook(
        payload(
            [
                msg(
                    "interactive",
                    interactive={
                        "type": "button_reply",
                        "button_reply": {"id": "yes", "title": "Yes"},
                    },
                ),
                msg(
                    "interactive",
                    interactive={
                        "type": "list_reply",
                        "list_reply": {"id": "doc:1", "title": "Dr. Amit"},
                    },
                ),
                msg("button", button={"payload": "confirm", "text": "Confirm"}),
            ]
        )
    )
    assert [(m.kind, m.choice_id, m.text) for m in batch.messages] == [
        (InboundKind.CHOICE, "yes", "Yes"),
        (InboundKind.CHOICE, "doc:1", "Dr. Amit"),
        (InboundKind.CHOICE, "confirm", "Confirm"),
    ]


def test_media_is_kept_but_marked_unsupported() -> None:
    [m] = parse_webhook(payload([msg("image", image={"id": "media-1"})])).messages
    assert m.kind is InboundKind.UNSUPPORTED


def test_statuses_including_failures() -> None:
    batch = parse_webhook(
        payload(
            statuses=[
                {"id": "wamid.out1", "status": "delivered", "timestamp": "1760000000"},
                {
                    "id": "wamid.out2",
                    "status": "failed",
                    "timestamp": "1760000000",
                    "errors": [{"code": 131047, "title": "Re-engagement message"}],
                },
                {"id": "wamid.out3", "status": "deleted"},  # unknown status: skipped
            ]
        )
    )
    assert [(s.wa_message_id, s.status) for s in batch.statuses] == [
        ("wamid.out1", DeliveryStatus.DELIVERED),
        ("wamid.out2", DeliveryStatus.FAILED),
    ]
    assert batch.statuses[1].error == "131047: Re-engagement message"


def test_other_objects_and_fields_are_ignored() -> None:
    assert parse_webhook({"object": "page"}).messages == []
    other_field = payload([msg("text", text={"body": "x"})])
    other_field["entry"][0]["changes"][0]["field"] = "account_update"
    assert parse_webhook(other_field).messages == []


def test_signature() -> None:
    body = b'{"object":"whatsapp_business_account"}'
    assert verify_signature("secret", body, sign("secret", body))
    assert not verify_signature("secret", body, sign("other", body))
    assert not verify_signature("secret", body, None)
    assert not verify_signature("secret", body + b" ", sign("secret", body))
