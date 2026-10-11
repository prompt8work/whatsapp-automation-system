"""A: WhatsApp Payments (India, UPI) - a "Review and pay" order message. The clinic links its
payment account once in WhatsApp Business Manager and names that configuration in Settings.
Results arrive on the WhatsApp webhook as statuses of type "payment" (PL-6.1 A)."""

from __future__ import annotations

from app.platform.payments.application.ports import GatewayResult, RazorpaySecrets
from app.platform.payments.domain.errors import PaymentsNotSetUpError, RefundNotSupportedError
from app.platform.payments.domain.payment import PaymentMethod, PaymentRequest, PaymentSettings
from app.shared.kernel.messages import OrderDetails, OutboundMessage


class WhatsAppPayGateway:
    method = PaymentMethod.WHATSAPP_PAY

    async def create(
        self, payment: PaymentRequest, settings: PaymentSettings, secrets: RazorpaySecrets | None
    ) -> GatewayResult:
        if not settings.whatsapp_pay_configuration:
            raise PaymentsNotSetUpError("Enter the WhatsApp Payments configuration name")
        # Nothing to call: the order message itself is the request. Its reference comes back.
        return GatewayResult(gateway_ref=payment.receipt_number)

    def message(
        self, payment: PaymentRequest, settings: PaymentSettings, body: str, button: str
    ) -> OutboundMessage | None:
        return OrderDetails(
            body=body,
            reference_id=payment.receipt_number,
            configuration=settings.whatsapp_pay_configuration,
            item_name=payment.purpose[:60],
            amount_minor=payment.amount_minor,
            currency=payment.currency,
        )

    async def refund(
        self, payment: PaymentRequest, settings: PaymentSettings, secrets: RazorpaySecrets | None
    ) -> None:
        raise RefundNotSupportedError(
            "Refund WhatsApp payments from your payment provider, then use Mark as refunded"
        )
