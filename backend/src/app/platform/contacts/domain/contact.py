"""Contact: one WhatsApp number within one tenant (PRD PL-2.1).

The same person messaging two clinics is two separate contacts - tenants never share data.
Modules attach their own profiles to a contact (e.g. several patients per contact, PL-2.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.platform.contacts.domain.events import (
    ConsentGranted,
    ContactCreated,
    ContactOptedIn,
    ContactOptedOut,
)
from app.platform.contacts.domain.phone import PhoneNumber
from app.shared.kernel.actor import Actor
from app.shared.kernel.entity import TenantAggregateRoot
from app.shared.kernel.ids import TenantId


@dataclass(kw_only=True, eq=False)
class Contact(TenantAggregateRoot):
    phone: PhoneNumber
    profile_name: str | None  # WhatsApp profile name; may change any time
    first_seen_at: datetime
    last_inbound_at: datetime | None = None
    consent_given_at: datetime | None = None
    opted_out_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: TenantId,
        phone: PhoneNumber,
        profile_name: str | None,
        at: datetime,
    ) -> Contact:
        contact = cls(
            id=id,
            tenant_id=tenant_id,
            phone=phone,
            profile_name=_clean_name(profile_name),
            first_seen_at=at,
        )
        contact.record(ContactCreated(occurred_at=at, contact_id=id))
        return contact

    @property
    def has_consent(self) -> bool:
        return self.consent_given_at is not None

    @property
    def is_opted_out(self) -> bool:
        """Opted out of reminders/promotions (PL-2.4). Replies to their own messages still go."""
        return self.opted_out_at is not None

    def record_inbound(self, at: datetime, profile_name: str | None) -> None:
        """Operational bookkeeping on every message - deliberately no event (too frequent)."""
        self.last_inbound_at = at
        if profile_name:
            self.profile_name = _clean_name(profile_name)

    def grant_consent(self, *, actor: Actor, at: datetime) -> None:
        if self.consent_given_at is None:
            self.consent_given_at = at
            self.record(ConsentGranted(occurred_at=at, contact_id=self.id, actor=actor))

    def opt_out(self, *, actor: Actor, at: datetime) -> None:
        if self.opted_out_at is None:
            self.opted_out_at = at
            self.record(ContactOptedOut(occurred_at=at, contact_id=self.id, actor=actor))

    def opt_in(self, *, actor: Actor, at: datetime) -> None:
        if self.opted_out_at is not None:
            self.opted_out_at = None
            self.record(ContactOptedIn(occurred_at=at, contact_id=self.id, actor=actor))


def _clean_name(name: str | None) -> str | None:
    cleaned = " ".join((name or "").split())[:120]
    return cleaned or None
