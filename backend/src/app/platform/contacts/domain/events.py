"""Contact events. Ids only - never the phone number or profile name."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.shared.kernel.actor import Actor
from app.shared.kernel.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ContactCreated(DomainEvent):
    contact_id: UUID


@dataclass(frozen=True, kw_only=True)
class ConsentGranted(DomainEvent):
    contact_id: UUID
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class ContactOptedOut(DomainEvent):
    contact_id: UUID
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class ContactOptedIn(DomainEvent):
    contact_id: UUID
    actor: Actor
