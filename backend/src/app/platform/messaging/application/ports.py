"""Ports the messaging use cases need."""

from __future__ import annotations

from typing import Protocol

from app.shared.kernel.messages import OutboundMessage


class SendError(Exception):
    """Sending failed. `transient` = worth retrying later (timeouts, 5xx, rate limits)."""

    def __init__(self, message: str, *, transient: bool, code: str | None = None) -> None:
        super().__init__(message)
        self.transient = transient
        self.code = code


class WhatsAppGateway(Protocol):
    """Implementations: MetaCloudGateway (production), RecordingGateway (local/tests)."""

    async def send(
        self, *, phone_number_id: str, access_token: str, to: str, message: OutboundMessage
    ) -> str:
        """Returns Meta's message id. Raises SendError."""
        ...
