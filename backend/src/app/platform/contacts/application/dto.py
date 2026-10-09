from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.platform.contacts.domain.contact import Contact


@dataclass(frozen=True)
class ContactDTO:
    id: UUID
    phone: str
    profile_name: str | None
    first_seen_at: datetime
    last_inbound_at: datetime | None
    has_consent: bool
    is_opted_out: bool

    @classmethod
    def from_domain(cls, c: Contact) -> ContactDTO:
        return cls(
            id=c.id,
            phone=c.phone.e164,
            profile_name=c.profile_name,
            first_seen_at=c.first_seen_at,
            last_inbound_at=c.last_inbound_at,
            has_consent=c.has_consent,
            is_opted_out=c.is_opted_out,
        )


@dataclass(frozen=True)
class ResolvedContact:
    contact: ContactDTO
    is_new: bool  # drives greeting rule R1 ("new number") in step 5
