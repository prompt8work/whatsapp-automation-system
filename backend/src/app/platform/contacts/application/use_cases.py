from __future__ import annotations

from dataclasses import dataclass

from app.platform.contacts.application.commands.preferences import GrantConsent, SetOptOut
from app.platform.contacts.application.commands.resolve_contact import ResolveContact
from app.platform.contacts.application.queries.contacts import GetContact, SearchContacts


@dataclass(frozen=True)
class ContactsUseCases:
    resolve: ResolveContact
    grant_consent: GrantConsent
    set_opt_out: SetOptOut
    search: SearchContacts
    get: GetContact
