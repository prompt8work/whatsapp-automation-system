"""Public surface of contacts for other modules (ARCHITECTURE §3.3).

The conversation pipeline (step 3) calls `contacts_for(services, tenant).resolve(...)` for
every incoming message, and `.grant_consent` / `.set_opt_out` for "Yes" / "STOP".
"""

from __future__ import annotations

from app.platform.contacts.application.commands.preferences import (
    GrantConsentCommand,
    SetOptOutCommand,
)
from app.platform.contacts.application.commands.resolve_contact import ResolveContactCommand
from app.platform.contacts.application.dto import ContactDTO, ResolvedContact
from app.platform.contacts.application.queries.contacts import SearchContactsQuery
from app.platform.contacts.application.use_cases import ContactsUseCases
from app.platform.contacts.wiring import contacts_use_cases as contacts_for

__all__ = [
    "ContactDTO",
    "ContactsUseCases",
    "GrantConsentCommand",
    "ResolveContactCommand",
    "ResolvedContact",
    "SearchContactsQuery",
    "SetOptOutCommand",
    "contacts_for",
]
