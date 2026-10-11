from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.platform.messaging.infrastructure.meta import render
from app.platform.messaging.infrastructure.webhook import parse_webhook
from app.platform.payments.domain.errors import InvalidPaymentTransitionError
from app.platform.payments.domain.payment import (
    PaymentMethod,
    PaymentRequest,
    PaymentSettings,
    PaymentStatus,
)
from app.platform.payments.infrastructure.gateways.razorpay import (
    parse_razorpay_webhook,
    verify_razorpay_signature,
)
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import LinkButton, OrderDetails

T0 = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)


def payment() -> PaymentRequest:
    return PaymentRequest.create(
        id=uuid4(),
        tenant_id=TenantId(uuid4()),
        subject_type="appointment",
        subject_id=uuid4(),
        contact_id=uuid4(),
        payer_name="Rahul Verma",
        payer_phone="+919800000000",
        purpose="Consultation APT-1",
        amount_minor=50000,
        currency="INR",
        method=PaymentMethod.AT_CLINIC,
        expires_at=None,
        at=T0,
    )


def test_paid_is_idempotent_and_only_paid_can_be_refunded() -> None:
    p = payment()
    with pytest.raises(InvalidPaymentTransitionError):
        p.mark_refunded(actor=Actor.system(), at=T0)
    assert p.mark_paid(actor=Actor.system(), at=T0, transaction_id="tx1") is True
    assert p.mark_paid(actor=Actor.system(), at=T0) is False  # webhook delivered twice
    assert p.expire(actor=Actor.system(), at=T0) is False  # paid stays paid
    assert p.mark_refunded(actor=Actor.system(), at=T0) is True
    assert [e.event_type for e in p.pull_events()] == [
        "PaymentRequested",
        "PaymentSucceeded",
        "PaymentRefunded",
    ]


def test_money_arriving_after_expiry_is_still_recorded() -> None:
    p = payment()
    p.expire(actor=Actor.system(), at=T0)
    assert p.is_settled
    assert p.mark_paid(actor=Actor.system(), at=T0) is True
    assert p.status is PaymentStatus.PAID


def test_detached_ledger_entry_keeps_the_receipt_details() -> None:  # RT-7
    p = payment()
    p.detach()
    assert (p.subject_id, p.contact_id) == (None, None)
    assert (p.payer_name, p.amount_minor, p.receipt_number) == (
        "Rahul Verma",
        50000,
        p.receipt_number,
    )


def test_primary_method_prefers_paying_in_the_chat() -> None:
    both = PaymentSettings(methods=(PaymentMethod.AT_CLINIC, PaymentMethod.RAZORPAY_LINK))
    assert both.primary_method is PaymentMethod.RAZORPAY_LINK
    assert PaymentSettings().primary_method is None


def test_razorpay_webhook_signature_and_events() -> None:
    body = json.dumps(
        {
            "event": "payment_link.paid",
            "payload": {
                "payment_link": {"entity": {"id": "plink_1"}},
                "payment": {"entity": {"id": "pay_1"}},
            },
        }
    ).encode()
    good = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_razorpay_signature("secret", body, good)
    assert not verify_razorpay_signature("secret", body, None)
    assert not verify_razorpay_signature("other", body, good)
    update = parse_razorpay_webhook(body)
    assert update is not None
    assert (update.kind, update.gateway_ref, update.transaction_id) == ("paid", "plink_1", "pay_1")
    refund = json.dumps(
        {"event": "refund.processed", "payload": {"refund": {"entity": {"payment_id": "pay_1"}}}}
    ).encode()
    assert parse_razorpay_webhook(refund) == type(update)("refunded", transaction_id="pay_1")
    assert parse_razorpay_webhook(b'{"event": "order.paid"}') is None


def test_whatsapp_payment_status_is_parsed_from_the_webhook() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "123"},
                            "statuses": [
                                {
                                    "id": "wamid.X",
                                    "status": "captured",
                                    "type": "payment",
                                    "timestamp": "1760000000",
                                    "payment": {
                                        "reference_id": "RC-ABC",
                                        "amount": {"value": 50000, "offset": 100},
                                        "transaction": {"id": "upi-1", "status": "success"},
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }
    batch = parse_webhook(payload)
    assert batch.statuses == []
    [notice] = batch.payments
    assert (notice.reference_id, notice.status, notice.transaction_id, notice.amount_minor) == (
        "RC-ABC",
        "captured",
        "upi-1",
        50000,
    )


def test_payment_messages_render_for_meta() -> None:
    order = render("9198", OrderDetails("Pay", "RC-ABC", "clinic-upi", "Consultation", 50000))
    params = order["interactive"]["action"]["parameters"]
    assert order["interactive"]["type"] == "order_details"
    assert (params["reference_id"], params["payment_configuration"]) == ("RC-ABC", "clinic-upi")
    assert params["total_amount"] == {"value": 50000, "offset": 100}
    link = render("9198", LinkButton("Pay", "Pay now", "https://rzp.io/i/x"))
    assert link["interactive"]["action"]["parameters"]["url"] == "https://rzp.io/i/x"
