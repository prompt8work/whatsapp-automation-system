from __future__ import annotations

from app.shared.kernel.errors import DomainError, NotFoundError


class PaymentNotFoundError(NotFoundError):
    code = "payments.not_found"


class InvalidPaymentTransitionError(DomainError):
    code = "payments.invalid_transition"


class PaymentsNotSetUpError(DomainError):
    """No payment method switched on, or the chosen one is missing its configuration."""

    code = "payments.not_set_up"


class PaymentGatewayError(DomainError):
    """The provider (Razorpay / Meta) refused or failed. Safe to show staff; never secrets."""

    code = "payments.gateway_error"


class RefundNotSupportedError(DomainError):
    """WhatsApp Payments and Pay at clinic: refund outside, then Mark as refunded (PL-6.5)."""

    code = "payments.refund_not_supported"
