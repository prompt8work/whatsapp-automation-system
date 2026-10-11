"""C: Pay at clinic - nothing to send; staff Mark as paid at the counter (PL-6.1)."""

from __future__ import annotations

from app.platform.payments.application.ports import GatewayResult, RazorpaySecrets
from app.platform.payments.domain.errors import RefundNotSupportedError
from app.platform.payments.domain.payment import PaymentMethod, PaymentRequest, PaymentSettings
from app.shared.kernel.messages import OutboundMessage


class AtClinicGateway:
    method = PaymentMethod.AT_CLINIC

    async def create(
        self, payment: PaymentRequest, settings: PaymentSettings, secrets: RazorpaySecrets | None
    ) -> GatewayResult:
        return GatewayResult()

    def message(
        self, payment: PaymentRequest, settings: PaymentSettings, body: str, button: str
    ) -> OutboundMessage | None:
        return None

    async def refund(
        self, payment: PaymentRequest, settings: PaymentSettings, secrets: RazorpaySecrets | None
    ) -> None:
        raise RefundNotSupportedError("Refund at the counter, then use Mark as refunded")
