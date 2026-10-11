"""What payments needs from the outside world - one port per kind of thing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.platform.payments.domain.payment import PaymentMethod, PaymentRequest, PaymentSettings
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import OutboundMessage


@dataclass(frozen=True)
class GatewayResult:
    gateway_ref: str | None = None
    pay_url: str | None = None


@dataclass(frozen=True)
class GatewayUpdate:
    """A verified status report from a provider (PL-6.4)."""

    kind: Literal["paid", "failed", "expired", "refunded"]
    gateway_ref: str | None = None  # payment-link id / WhatsApp reference_id
    transaction_id: str | None = None  # provider payment / transaction id


@dataclass(frozen=True)
class RazorpaySecrets:
    key_secret: str
    webhook_secret: str


class PaymentGateway(Protocol):
    """One payment method (ARCHITECTURE §8.6). No use case knows which one it talks to."""

    method: PaymentMethod

    async def create(
        self, payment: PaymentRequest, settings: PaymentSettings, secrets: RazorpaySecrets | None
    ) -> GatewayResult:
        """Set the payment up at the provider (e.g. create the Razorpay link)."""
        ...

    def message(
        self, payment: PaymentRequest, settings: PaymentSettings, body: str, button: str
    ) -> OutboundMessage | None:
        """What the patient taps to pay; None for Pay at clinic."""
        ...

    async def refund(
        self, payment: PaymentRequest, settings: PaymentSettings, secrets: RazorpaySecrets | None
    ) -> None:
        """Raises RefundNotSupportedError where the clinic refunds outside the system."""
        ...


class PaymentSettingsStore(Protocol):
    async def get(self, tenant_id: TenantId) -> PaymentSettings: ...

    async def put(self, tenant_id: TenantId, settings: PaymentSettings) -> None: ...

    async def secrets(self, tenant_id: TenantId) -> RazorpaySecrets | None: ...

    async def put_secrets(self, tenant_id: TenantId, secrets: RazorpaySecrets) -> None:
        """Encrypted at rest; never returned to the dashboard."""
        ...
