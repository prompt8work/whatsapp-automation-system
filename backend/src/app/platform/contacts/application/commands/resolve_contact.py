"""Find the contact for an incoming WhatsApp message, creating it on first contact.

Called by the inbound pipeline (step 3) for EVERY message. Two messages from a new number
can arrive at the same moment; the unique (tenant, phone) constraint makes one insert lose,
and the loser simply loads the winner's row.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.platform.contacts.application.dto import ContactDTO, ResolvedContact
from app.platform.contacts.application.unit_of_work import ContactsUnitOfWork
from app.platform.contacts.domain.contact import Contact
from app.platform.contacts.domain.phone import PhoneNumber
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId


@dataclass(frozen=True)
class ResolveContactCommand:
    tenant_id: TenantId
    wa_id: str  # WhatsApp sender id, e.g. "919876543210"
    profile_name: str | None = None


class ResolveContact:
    def __init__(self, uow: ContactsUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        self._uow, self._clock, self._ids = uow, clock, ids

    async def __call__(self, cmd: ResolveContactCommand) -> ResolvedContact:
        phone = PhoneNumber.parse(cmd.wa_id)
        now = self._clock.now()
        async with self._uow as uow:
            contact = await uow.contacts.find_by_phone(phone)
            is_new = contact is None
            if contact is None:
                contact = Contact.create(
                    id=self._ids.new_id(),
                    tenant_id=cmd.tenant_id,
                    phone=phone,
                    profile_name=cmd.profile_name,
                    at=now,
                )
                if not await uow.contacts.add(contact):  # lost the race
                    is_new = False
                    found = await uow.contacts.find_by_phone(phone)
                    assert found is not None
                    contact = found
            contact.record_inbound(now, cmd.profile_name)
            await uow.contacts.save(contact)
            await uow.commit()
        return ResolvedContact(ContactDTO.from_domain(contact), is_new=is_new)
