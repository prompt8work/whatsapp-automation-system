"""B: Razorpay payment links (PL-6.1 B). The clinic's own keys; money goes straight to it.

Create:  POST /v1/payment_links            -> {id: "plink_...", short_url}
Refund:  POST /v1/payments/{id}/refund
Webhook: POST /webhooks/razorpay/{tenant_id}, X-Razorpay-Signature = HMAC-SHA256(body, secret)
         payment_link.paid | payment_link.expired | payment_link.cancelled | refund.processed
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx
import structlog

from app.platform.payments.application.ports import (
    GatewayResult,
    GatewayUpdate,
    RazorpaySecrets,
)
from app.platform.payments.domain.errors import PaymentGatewayError, PaymentsNotSetUpError
from app.platform.payments.domain.payment import PaymentMethod, PaymentRequest, PaymentSettings
from app.shared.kernel.messages import LinkButton, OutboundMessage

log = structlog.get_logger(__name__)
API = "https://api.razorpay.com/v1"
MIN_EXPIRY_SECONDS = 16 * 60  # Razorpay wants expire_by at least 15 minutes ahead


class RazorpayLinkGateway:
    method = PaymentMethod.RAZORPAY_LINK

    def __init__(self, client: httpx.AsyncClient, api: str = API) -> None:
        self._client, self._api = client, api

    @staticmethod
    def _auth(settings: PaymentSettings, secrets: RazorpaySecrets | None) -> tuple[str, str]:
        if not settings.razorpay_key_id or secrets is None:
            raise PaymentsNotSetUpError("Enter the Razorpay key id and secrets in Settings")
        return settings.razorpay_key_id, secrets.key_secret

    async def _post(self, path: str, body: dict[str, Any], auth: tuple[str, str]) -> dict[str, Any]:
        try:
            response = await self._client.post(f"{self._api}{path}", json=body, auth=auth)
        except httpx.HTTPError as exc:
            raise PaymentGatewayError("Razorpay could not be reached; try again") from exc
        if response.status_code >= 400:
            error = (response.json() if response.content else {}).get("error") or {}
            log.warning("razorpay.error", status=response.status_code, code=error.get("code"))
            raise PaymentGatewayError(f"Razorpay: {error.get('description') or 'request failed'}")
        data: dict[str, Any] = response.json()
        return data

    async def create(
        self, payment: PaymentRequest, settings: PaymentSettings, secrets: RazorpaySecrets | None
    ) -> GatewayResult:
        body: dict[str, Any] = {
            "amount": payment.amount_minor,
            "currency": payment.currency,
            "accept_partial": False,
            "reference_id": payment.receipt_number,
            "description": payment.purpose,
            "customer": {"name": payment.payer_name, "contact": payment.payer_phone},
            "notify": {"sms": False, "email": False},  # we send it on WhatsApp ourselves
            "reminder_enable": False,
            "notes": {"payment_id": str(payment.id)},
        }
        if payment.expires_at is not None:
            expire_by = int(payment.expires_at.timestamp())
            if expire_by - int(payment.created_at.timestamp()) >= MIN_EXPIRY_SECONDS:
                body["expire_by"] = expire_by
        link = await self._post("/payment_links", body, self._auth(settings, secrets))
        return GatewayResult(gateway_ref=str(link["id"]), pay_url=str(link["short_url"]))

    def message(
        self, payment: PaymentRequest, settings: PaymentSettings, body: str, button: str
    ) -> OutboundMessage | None:
        return LinkButton(body, button, payment.pay_url) if payment.pay_url else None

    async def refund(
        self, payment: PaymentRequest, settings: PaymentSettings, secrets: RazorpaySecrets | None
    ) -> None:
        if not payment.transaction_id:
            raise PaymentGatewayError("Razorpay has not reported the payment id yet")
        await self._post(
            f"/payments/{payment.transaction_id}/refund",
            {"amount": payment.amount_minor, "notes": {"receipt": payment.receipt_number}},
            self._auth(settings, secrets),
        )


def verify_razorpay_signature(webhook_secret: str, body: bytes, signature: str | None) -> bool:
    expected = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature or "")


def parse_razorpay_webhook(body: bytes) -> GatewayUpdate | None:
    """Only the events we act on; everything else is acknowledged and ignored."""
    try:
        data = json.loads(body)
    except ValueError:
        return None
    event, payload = data.get("event"), data.get("payload") or {}

    def entity(name: str) -> dict[str, Any]:
        found: dict[str, Any] = (payload.get(name) or {}).get("entity") or {}
        return found

    if event == "payment_link.paid":
        return GatewayUpdate(
            "paid",
            gateway_ref=entity("payment_link").get("id"),
            transaction_id=entity("payment").get("id"),
        )
    if event in ("payment_link.expired", "payment_link.cancelled"):
        return GatewayUpdate("expired", gateway_ref=entity("payment_link").get("id"))
    if event == "refund.processed":
        return GatewayUpdate("refunded", transaction_id=entity("refund").get("payment_id"))
    return None
