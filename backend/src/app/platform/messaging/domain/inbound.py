"""What arrived from WhatsApp, already parsed from Meta's webhook JSON (by infrastructure)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class InboundKind(StrEnum):
    TEXT = "text"
    CHOICE = "choice"  # tapped a reply button, list row or template quick-reply
    UNSUPPORTED = "unsupported"  # image, audio, location, sticker ... (v1 asks for text)


@dataclass(frozen=True)
class InboundMessage:
    phone_number_id: str  # which of OUR numbers received it -> tenant
    wa_message_id: str  # Meta's id - dedupe key
    wa_id: str  # sender, e.g. "919876543210"
    profile_name: str | None
    sent_at: datetime
    kind: InboundKind
    text: str  # typed text, or the tapped choice's title
    choice_id: str | None = None  # the Choice.id we sent, when kind is CHOICE


class DeliveryStatus(StrEnum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


@dataclass(frozen=True)
class StatusUpdate:
    phone_number_id: str
    wa_message_id: str
    status: DeliveryStatus
    at: datetime
    error: str | None = None


@dataclass(frozen=True)
class WebhookBatch:
    messages: list[InboundMessage]
    statuses: list[StatusUpdate]
