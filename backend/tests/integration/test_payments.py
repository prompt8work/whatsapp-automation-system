"""Payments (PRD §6.6, §7.5) against PostgreSQL: the three methods end to end, staff actions,
receipts, R6 in the menu, and the retention rules RT-6 / RT-7. Razorpay is a mock transport."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.platform.messaging.contracts import PaymentNotice, WebhookBatch
from tests.integration.conftest import Api, ApiFactory
from tests.integration.test_appointment_bot import Chat, book_tomorrow, clinic, tick
from tests.integration.test_retention import run_retention, tenant_of

pytestmark = pytest.mark.db

WEBHOOK_SECRET = "whsec-integration-1"


class FakeRazorpay:
    """Just enough of api.razorpay.com: payment links and refunds."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        self.calls.append((request.url.path, body))
        if request.url.path == "/v1/payment_links":
            return httpx.Response(
                200, json={"id": "plink_TEST1", "short_url": "https://rzp.io/i/test1"}
            )
        if request.url.path.endswith("/refund"):
            return httpx.Response(200, json={"id": "rfnd_1", "status": "processed"})
        return httpx.Response(404, json={"error": {"description": "unknown"}})


async def paying_clinic(
    api: Api, methods: list[str], **payment_settings: str
) -> tuple[dict[str, str], str]:
    admin, number = await clinic(api)
    rules = (await api.client.get("/api/appointments/settings", headers=admin)).json()
    saved = await api.client.put(
        "/api/appointments/settings", json=rules | {"consultation_fee": 500}, headers=admin
    )
    assert saved.status_code == 200, saved.text
    body = {"methods": methods} | payment_settings
    response = await api.client.put("/api/payments/settings", json=body, headers=admin)
    assert response.status_code == 204, response.text
    return admin, number


async def confirmed_booking(
    api: Api, admin: dict[str, str], number: str
) -> tuple[Chat, dict[str, Any]]:
    chat = Chat(api, number)
    await chat.send("Hi")
    await chat.tap("Yes")
    await chat.send("Rahul Verma")
    await book_tomorrow(chat)
    [appointment] = (await api.client.get("/api/appointments/requests", headers=admin)).json()
    approved = await api.client.post(
        f"/api/appointments/{appointment['id']}/approve", headers=admin
    )
    assert approved.status_code == 200
    await tick(api)  # -> "Confirmed ✅", then the payment request
    return chat, appointment


async def payment_of(api: Api, admin: dict[str, str], appointment_id: str) -> dict[str, Any]:
    [payment] = (
        await api.client.get(f"/api/payments?subject_id={appointment_id}", headers=admin)
    ).json()
    return payment


async def test_pay_at_clinic_staff_mark_paid_and_receipt(api: Api) -> None:
    admin, number = await paying_clinic(api, ["at_clinic"])
    chat, appointment = await confirmed_booking(api, admin, number)
    assert "₹500, payable at the clinic" in chat.inbox()[-1]

    payment = await payment_of(api, admin, appointment["id"])
    assert (payment["method"], payment["status"], payment["amount_minor"]) == (
        "at_clinic",
        "pending",
        50000,
    )
    assert payment["payer_name"] == "Rahul Verma"
    assert payment["purpose"] == f"Consultation {appointment['reference']}"

    paid = await api.client.post(
        f"/api/payments/{payment['id']}/mark-paid", json={"note": "cash"}, headers=admin
    )
    assert paid.json()["status"] == "paid"
    await tick(api)
    assert f"Payment received ✅ ₹500 for {appointment['reference']}" in chat.inbox()[-1]
    assert payment["receipt_number"] in chat.inbox()[-1]

    refund = await api.client.post(f"/api/payments/{payment['id']}/refund", json={}, headers=admin)
    assert refund.status_code == 409  # at the counter: refund there, then Mark as refunded
    marked = await api.client.post(
        f"/api/payments/{payment['id']}/mark-refunded", json={}, headers=admin
    )
    assert marked.json()["status"] == "refunded"


async def test_razorpay_link_webhook_and_refund(make_api: ApiFactory) -> None:
    razorpay = FakeRazorpay()
    api = await make_api(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(razorpay)),
        credentials_key=SecretStr(Fernet.generate_key().decode()),
    )
    admin, number = await paying_clinic(api, ["razorpay_link"], razorpay_key_id="rzp_test_1")
    secrets = await api.client.put(
        "/api/payments/settings/razorpay-secrets",
        json={"key_secret": "secret-123456", "webhook_secret": WEBHOOK_SECRET},
        headers=admin,
    )
    assert secrets.status_code == 204
    settings = (await api.client.get("/api/payments/settings", headers=admin)).json()
    assert settings["razorpay_secrets_saved"] is True
    assert "secret-123456" not in json.dumps(settings)  # write-only

    chat, appointment = await confirmed_booking(api, admin, number)
    assert "[Pay now] https://rzp.io/i/test1" in chat.inbox()[-1]
    [(path, link)] = razorpay.calls
    assert (path, link["amount"], link["customer"]["name"]) == (
        "/v1/payment_links",
        50000,
        "Rahul Verma",
    )

    event = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {"entity": {"id": "plink_TEST1"}},
            "payment": {"entity": {"id": "pay_TEST1"}},
        },
    }
    raw = json.dumps(event).encode()
    url = settings["razorpay_webhook_path"]
    forged = await api.client.post(url, content=raw, headers={"X-Razorpay-Signature": "nope"})
    assert forged.status_code == 401  # PL-6.4: only signed webhooks change a payment
    signature = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    for _ in range(2):  # Razorpay retries: the second delivery changes nothing
        response = await api.client.post(
            url, content=raw, headers={"X-Razorpay-Signature": signature}
        )
        assert response.status_code == 200
    assert response.json() == {"changed": False}

    payment = await payment_of(api, admin, appointment["id"])
    assert (payment["status"], payment["transaction_id"]) == ("paid", "pay_TEST1")
    await tick(api)
    assert "Payment received ✅" in chat.inbox()[-1]

    refunded = await api.client.post(
        f"/api/payments/{payment['id']}/refund", json={}, headers=admin
    )
    assert refunded.json()["status"] == "refunded"
    assert razorpay.calls[-1][0] == "/v1/payments/pay_TEST1/refund"
    await tick(api)
    assert "has been refunded" in chat.inbox()[-1]


async def test_whatsapp_pay_and_pay_now_in_the_menu(api: Api) -> None:  # PL-6.1 A, R6
    admin, number = await paying_clinic(
        api, ["whatsapp_pay", "at_clinic"], whatsapp_pay_configuration="clinic-upi"
    )
    chat, appointment = await confirmed_booking(api, admin, number)
    assert "[Review and pay 500.00 INR]" in chat.inbox()[-1]
    payment = await payment_of(api, admin, appointment["id"])
    assert payment["method"] == "whatsapp_pay"

    [menu] = await chat.send("Hi")
    assert f"₹500 due for {appointment['reference']}" in menu
    assert "1. Pay now" in menu
    [order] = await chat.tap("Pay now")
    assert "Review and pay" in order

    notice = PaymentNotice(
        phone_number_id=number,
        reference_id=payment["receipt_number"],
        status="captured",
        transaction_id="upi-123",
        amount_minor=50000,
        at=datetime.now(UTC),
    )
    report = await api.app.state.platform.conversations.handle_webhook(
        WebhookBatch(messages=[], statuses=[], payments=[notice])
    )
    assert report.payments == 1
    assert (await payment_of(api, admin, appointment["id"]))["status"] == "paid"
    await tick(api)
    assert "Payment received ✅" in chat.inbox()[-1]
    [menu] = await chat.send("Hi")
    assert "Pay now" not in menu  # nothing due any more


async def test_cancelled_appointment_payment_expires(api: Api) -> None:  # PL-6.5
    admin, number = await paying_clinic(api, ["at_clinic"])
    _, appointment = await confirmed_booking(api, admin, number)
    await api.client.post(
        f"/api/appointments/{appointment['id']}/cancel", json={"reason": ""}, headers=admin
    )
    await tick(api)
    assert (await payment_of(api, admin, appointment["id"]))["status"] == "expired"


async def cancel_and_close(api: Api, admin: dict[str, str], appointment: dict[str, Any]) -> None:
    cancelled = await api.client.post(
        f"/api/appointments/{appointment['id']}/cancel", json={"reason": ""}, headers=admin
    )
    assert cancelled.status_code == 200
    closed = await api.client.post(
        f"/api/cases/{appointment['case_id']}/close", json={}, headers=admin
    )
    assert closed.status_code == 200


async def test_pending_payment_blocks_the_purge(api: Api) -> None:  # RT-6
    admin, number = await paying_clinic(api, ["at_clinic"])
    _, appointment = await confirmed_booking(api, admin, number)
    tenant_id = await tenant_of(api, admin)
    await cancel_and_close(api, admin, appointment)  # no tick yet: the payment is still pending

    assert (await run_retention(api, tenant_id, days_from_now=61)).purged == 0
    await tick(api)  # cancellation -> the payment expires (PL-6.5)
    assert (await payment_of(api, admin, appointment["id"]))["status"] == "expired"
    assert (await run_retention(api, tenant_id, days_from_now=61)).purged >= 1


async def test_paid_payment_survives_the_purge_as_a_ledger_entry(api: Api) -> None:  # RT-7
    admin, number = await paying_clinic(api, ["at_clinic"])
    _, appointment = await confirmed_booking(api, admin, number)
    tenant_id = await tenant_of(api, admin)
    payment = await payment_of(api, admin, appointment["id"])
    await api.client.post(f"/api/payments/{payment['id']}/mark-paid", json={}, headers=admin)
    await cancel_and_close(api, admin, appointment)
    await tick(api)

    assert (await run_retention(api, tenant_id, days_from_now=61)).purged >= 1
    await tick(api)  # CasePurged -> payments detach their records
    ledger = (await api.client.get("/api/payments", headers=admin)).json()
    entry = next(p for p in ledger if p["id"] == payment["id"])
    assert (entry["subject_id"], entry["status"], entry["payer_name"], entry["amount_minor"]) == (
        None,
        "paid",
        "Rahul Verma",
        50000,
    )
