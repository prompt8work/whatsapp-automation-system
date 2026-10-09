from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter

from app.platform.contacts.application.commands.preferences import GrantConsent, SetOptOut
from app.platform.contacts.application.commands.resolve_contact import ResolveContact
from app.platform.contacts.application.queries.contacts import GetContact, SearchContacts
from app.platform.contacts.application.use_cases import ContactsUseCases
from app.platform.contacts.infrastructure.unit_of_work import SqlContactsUnitOfWork
from app.platform.contacts.presentation.http.routers import build_router
from app.shared.kernel.ids import TenantId
from app.shared.module import PlatformServices


def contacts_use_cases(services: PlatformServices, tenant_id: TenantId) -> ContactsUseCases:
    """Also used by contracts.py so other modules (the conversation pipeline) get the same."""
    uow = SqlContactsUnitOfWork(services.session_factory, tenant_id)
    clock, audit = services.clock, services.audit
    return ContactsUseCases(
        resolve=ResolveContact(uow, clock, services.ids),
        grant_consent=GrantConsent(uow, clock, audit),
        set_opt_out=SetOptOut(uow, clock, audit),
        search=SearchContacts(uow, audit),
        get=GetContact(uow, audit),
    )


def build_routers(services: PlatformServices) -> Sequence[APIRouter]:
    return [build_router(lambda tenant_id: contacts_use_cases(services, tenant_id))]
