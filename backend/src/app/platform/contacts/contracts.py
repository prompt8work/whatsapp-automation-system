"""Public TYPES of contacts for other modules (framework-free). The use-case factory for
other modules' wiring is in `integration.py`."""

from __future__ import annotations

from app.platform.contacts.application.commands.preferences import (
    GrantConsentCommand,
    SetOptOutCommand,
)
from app.platform.contacts.application.commands.resolve_contact import (
    EnsureContactCommand,
    ResolveContactCommand,
)
from app.platform.contacts.application.dto import ContactDTO, ResolvedContact
from app.platform.contacts.application.queries.contacts import GetContactQuery, SearchContactsQuery
from app.platform.contacts.application.use_cases import ContactsUseCases

__all__ = [
    "ContactDTO",
    "ContactsUseCases",
    "EnsureContactCommand",
    "GetContactQuery",
    "GrantConsentCommand",
    "ResolveContactCommand",
    "ResolvedContact",
    "SearchContactsQuery",
    "SetOptOutCommand",
]
