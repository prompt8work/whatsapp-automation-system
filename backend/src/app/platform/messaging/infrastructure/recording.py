"""Gateway that sends nothing: it remembers and logs messages. Used locally
(WHATSAPP_SENDER=recording), by `cli simulate`, and in tests."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import structlog

from app.platform.messaging.application.ports import SendError
from app.shared.kernel.messages import OutboundMessage

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SentMessage:
    phone_number_id: str
    to: str
    message: OutboundMessage
    wa_message_id: str


class RecordingGateway:
    def __init__(self) -> None:
        self.sent: list[SentMessage] = []
        self.fail_next: SendError | None = None  # tests: make the next send fail

    async def send(
        self, *, phone_number_id: str, access_token: str, to: str, message: OutboundMessage
    ) -> str:
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error
        # Unique like Meta's ids - the message log has a unique index on them.
        wa_message_id = f"wamid.recorded.{uuid4().hex}"
        self.sent.append(SentMessage(phone_number_id, to, message, wa_message_id))
        log.info("whatsapp.recorded", kind=type(message).__name__)  # no recipient/content: PII
        return wa_message_id

    def texts_to(self, to: str) -> list[str]:
        return [s.message.as_text() for s in self.sent if s.to == to.lstrip("+")]
