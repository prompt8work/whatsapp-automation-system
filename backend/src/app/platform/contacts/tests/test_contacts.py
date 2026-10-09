from __future__ import annotations

import copy
from uuid import UUID

import pytest

from app.platform.contacts.application.commands.preferences import SetOptOut, SetOptOutCommand
from app.platform.contacts.application.commands.resolve_contact import (
    ResolveContact,
    ResolveContactCommand,
)
from app.platform.contacts.domain.contact import Contact
from app.platform.contacts.domain.errors import ContactNotFoundError, InvalidPhoneNumberError
from app.platform.contacts.domain.events import ContactCreated, ContactOptedOut
from app.platform.contacts.domain.phone import PhoneNumber
from app.shared.application.audit import AuditRecord
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.testing.fakes import FixedClock, InMemoryUnitOfWork, SequentialIds

CLINIC = TenantId(UUID(int=7))


@pytest.mark.parametrize(
    ("raw", "e164"),
    [
        ("919876543210", "+919876543210"),  # WhatsApp wa_id
        ("+91 98765-43210", "+919876543210"),
        ("0091 98765 43210", "+919876543210"),
        ("9876543210", "+919876543210"),  # national -> default country code
        ("09876543210", "+919876543210"),  # national with trunk 0
        ("+1 (415) 555-0100", "+14155550100"),
    ],
)
def test_phone_numbers_normalise_to_e164(raw: str, e164: str) -> None:
    assert PhoneNumber.parse(raw).e164 == e164


@pytest.mark.parametrize("bad", ["", "abc", "+12", "0987654321", "+1234567890123456"])
def test_invalid_phone_numbers(bad: str) -> None:
    with pytest.raises(InvalidPhoneNumberError):
        PhoneNumber.parse(bad)


def test_masked_phone_hides_the_middle() -> None:
    assert PhoneNumber("+919876543210").masked() == "+91•••••43210"


# ------------------------------------------------------------------ fakes
class InMemoryContacts:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self.rows: dict[UUID, Contact] = {}
        self.lose_next_insert_race: Contact | None = None

    def _snapshot(self, c: Contact) -> Contact:
        stored = copy.deepcopy(c)
        stored.pull_events()
        return stored

    async def get(self, contact_id: UUID) -> Contact:
        if contact_id not in self.rows:
            raise ContactNotFoundError()
        return self._snapshot(self.rows[contact_id])

    async def find_by_phone(self, phone: PhoneNumber) -> Contact | None:
        found = next((c for c in self.rows.values() if c.phone == phone), None)
        return self._snapshot(found) if found else None

    async def search(self, text: str | None, *, limit: int, offset: int) -> list[Contact]:
        return list(self.rows.values())[offset : offset + limit]

    async def add(self, contact: Contact) -> bool:
        if self.lose_next_insert_race is not None:  # another request inserted first
            winner, self.lose_next_insert_race = self.lose_next_insert_race, None
            self.rows[winner.id] = winner
            return False
        self.rows[contact.id] = self._snapshot(contact)
        self._uow.track(contact)
        return True

    async def save(self, contact: Contact) -> None:
        contact.version += 1
        self.rows[contact.id] = self._snapshot(contact)
        self._uow.track(contact)


class InMemoryContactsUoW(InMemoryUnitOfWork):
    def __init__(self) -> None:
        super().__init__()
        self.contacts = InMemoryContacts(self)


class RecordingAudit:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    async def record(self, entry: AuditRecord) -> None:
        self.records.append(entry)


# ------------------------------------------------------------------ use cases
async def test_first_message_creates_contact_second_reuses_it() -> None:
    uow, clock = InMemoryContactsUoW(), FixedClock()
    resolve = ResolveContact(uow, clock, SequentialIds())

    first = await resolve(ResolveContactCommand(CLINIC, "919876543210", "Rahul"))
    second = await resolve(ResolveContactCommand(CLINIC, "+91 98765 43210", "Rahul V"))

    assert first.is_new
    assert not second.is_new
    assert first.contact.id == second.contact.id
    assert second.contact.profile_name == "Rahul V"
    assert [type(e) for e in uow.committed_events] == [ContactCreated]


async def test_losing_the_insert_race_returns_the_winner() -> None:
    uow, clock = InMemoryContactsUoW(), FixedClock()
    winner = Contact(
        id=UUID(int=999),
        tenant_id=CLINIC,
        phone=PhoneNumber("+919876543210"),
        profile_name=None,
        first_seen_at=clock.now(),
    )
    uow.contacts.lose_next_insert_race = winner

    resolved = await ResolveContact(uow, clock, SequentialIds())(
        ResolveContactCommand(CLINIC, "919876543210")
    )

    assert resolved.contact.id == winner.id
    assert not resolved.is_new


async def test_opt_out_is_recorded_and_audited() -> None:
    uow, clock, audit = InMemoryContactsUoW(), FixedClock(), RecordingAudit()
    resolved = await ResolveContact(uow, clock, SequentialIds())(
        ResolveContactCommand(CLINIC, "919876543210")
    )
    actor = Actor.contact(resolved.contact.id)

    dto = await SetOptOut(uow, clock, audit)(
        SetOptOutCommand(CLINIC, resolved.contact.id, opted_out=True, actor=actor)
    )

    assert dto.is_opted_out
    assert isinstance(uow.committed_events[-1], ContactOptedOut)
    assert [r.action for r in audit.records] == ["contact.opt_out"]
