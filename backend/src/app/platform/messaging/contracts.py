"""Public TYPES of messaging for other modules - framework-free, safe to import from any
layer (including other modules' application layers).

Wiring-level helpers (use-case factories, webhook parsing) are in `integration.py`, for other
modules' wiring/presentation only. Feature modules usually need neither: they send through
the shared `Messenger` port using the types in `app.shared.kernel.messages`.
"""

from __future__ import annotations

from app.platform.messaging.application.commands.inbound import RecordInboundCommand
from app.platform.messaging.domain.inbound import (
    DeliveryStatus,
    InboundKind,
    InboundMessage,
    PaymentNotice,
    StatusUpdate,
    WebhookBatch,
)

__all__ = [
    "DeliveryStatus",
    "InboundKind",
    "InboundMessage",
    "PaymentNotice",
    "RecordInboundCommand",
    "StatusUpdate",
    "WebhookBatch",
]
