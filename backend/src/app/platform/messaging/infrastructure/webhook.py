"""Meta webhook: signature check + payload parsing.

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
Anything we do not understand is skipped (never crash on a new Meta field).
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any

from app.platform.messaging.domain.inbound import (
    DeliveryStatus,
    InboundKind,
    InboundMessage,
    PaymentNotice,
    StatusUpdate,
    WebhookBatch,
)


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """X-Hub-Signature-256: "sha256=<hex hmac of the raw body with the app secret>"."""
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def sign(app_secret: str, body: bytes) -> str:
    """For tests and the local simulator."""
    return "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()


def parse_webhook(payload: dict[str, Any]) -> WebhookBatch:
    batch = WebhookBatch(messages=[], statuses=[])
    if payload.get("object") != "whatsapp_business_account":
        return batch
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            if change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            phone_number_id = str((value.get("metadata") or {}).get("phone_number_id", ""))
            if not phone_number_id:
                continue
            names = {
                c.get("wa_id"): (c.get("profile") or {}).get("name")
                for c in value.get("contacts") or []
            }
            for raw in value.get("messages") or []:
                message = _message(phone_number_id, raw, names)
                if message:
                    batch.messages.append(message)
            for raw in value.get("statuses") or []:
                if raw.get("type") == "payment":
                    notice = _payment(phone_number_id, raw)
                    if notice:
                        batch.payments.append(notice)
                    continue
                status = _status(phone_number_id, raw)
                if status:
                    batch.statuses.append(status)
    return batch


def _ts(raw: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(raw), UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _message(
    phone_number_id: str, raw: dict[str, Any], names: dict[Any, Any]
) -> InboundMessage | None:
    wa_id, message_id = raw.get("from"), raw.get("id")
    if not wa_id or not message_id:
        return None
    kind, text, choice_id = InboundKind.UNSUPPORTED, "", None
    match raw.get("type"):
        case "text":
            kind, text = InboundKind.TEXT, str((raw.get("text") or {}).get("body", ""))
        case "interactive":
            interactive = raw.get("interactive") or {}
            reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
            if reply.get("id"):
                kind, text, choice_id = (
                    InboundKind.CHOICE,
                    str(reply.get("title", "")),
                    str(reply["id"]),
                )
        case "button":  # quick-reply button on a template
            button = raw.get("button") or {}
            kind, text = InboundKind.CHOICE, str(button.get("text", ""))
            choice_id = str(button.get("payload") or button.get("text") or "")
    return InboundMessage(
        phone_number_id=phone_number_id,
        wa_message_id=str(message_id),
        wa_id=str(wa_id),
        profile_name=names.get(wa_id),
        sent_at=_ts(raw.get("timestamp")),
        kind=kind,
        text=text.strip(),
        choice_id=choice_id,
    )


def _status(phone_number_id: str, raw: dict[str, Any]) -> StatusUpdate | None:
    try:
        status = DeliveryStatus(str(raw.get("status")))
    except ValueError:
        return None
    if not raw.get("id"):
        return None
    errors = raw.get("errors") or []
    error = None
    if errors:
        first = errors[0]
        error = f"{first.get('code')}: {first.get('title') or first.get('message') or ''}"
    return StatusUpdate(
        phone_number_id=phone_number_id,
        wa_message_id=str(raw["id"]),
        status=status,
        at=_ts(raw.get("timestamp")),
        error=error,
    )


def _payment(phone_number_id: str, raw: dict[str, Any]) -> PaymentNotice | None:
    payment = raw.get("payment") or {}
    reference_id = payment.get("reference_id")
    if not reference_id:
        return None
    amount = payment.get("amount") or {}
    value, offset = amount.get("value"), amount.get("offset") or 100
    transaction = payment.get("transaction") or {}
    return PaymentNotice(
        phone_number_id=phone_number_id,
        reference_id=str(reference_id),
        status=str(raw.get("status", "")),
        transaction_id=str(transaction["id"]) if transaction.get("id") else None,
        amount_minor=int(value) * 100 // int(offset) if value is not None else None,
        at=_ts(raw.get("timestamp")),
    )
