"""Who made a change, and through which channel (PRD AP-8.2).

The bot, the dashboard and the scheduler call the SAME use cases;
only `Actor` and `Channel` differ.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ActorKind(StrEnum):
    CONTACT = "contact"
    STAFF = "staff"
    SYSTEM = "system"


class Channel(StrEnum):
    WHATSAPP = "whatsapp"
    DASHBOARD = "dashboard"
    SCHEDULER = "scheduler"


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    id: UUID | None = None

    @classmethod
    def contact(cls, contact_id: UUID) -> Actor:
        return cls(ActorKind.CONTACT, contact_id)

    @classmethod
    def staff(cls, user_id: UUID) -> Actor:
        return cls(ActorKind.STAFF, user_id)

    @classmethod
    def system(cls) -> Actor:
        return cls(ActorKind.SYSTEM)

    def __str__(self) -> str:
        return f"{self.kind}:{self.id}" if self.id else str(self.kind)
