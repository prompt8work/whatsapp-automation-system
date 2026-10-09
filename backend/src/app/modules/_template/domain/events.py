"""Domain events. Past tense, one per business change; they double as the history."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.shared.kernel.actor import Actor
from app.shared.kernel.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ItemCreated(DomainEvent):
    item_id: UUID
    name: str
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class ItemRenamed(DomainEvent):
    item_id: UUID
    old_name: str
    new_name: str
    actor: Actor
