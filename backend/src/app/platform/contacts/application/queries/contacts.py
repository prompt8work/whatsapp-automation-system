"""Reading contacts returns personal data (phone numbers), so every read is audited."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.platform.contacts.application.dto import ContactDTO
from app.platform.contacts.application.unit_of_work import ContactsUnitOfWork
from app.shared.application.audit import AuditLogger, AuditRecord
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class SearchContactsQuery:
    tenant_id: TenantId
    actor: Actor
    text: str | None = None
    limit: int = 50
    offset: int = 0


class SearchContacts:
    def __init__(self, uow: ContactsUnitOfWork, audit: AuditLogger) -> None:
        self._uow, self._audit = uow, audit

    async def __call__(self, query: SearchContactsQuery) -> list[ContactDTO]:
        limit = max(1, min(query.limit, MAX_PAGE_SIZE))
        async with self._uow as uow:
            found = await uow.contacts.search(query.text, limit=limit, offset=max(0, query.offset))
        await self._audit.record(
            AuditRecord(
                query.tenant_id,
                query.actor,
                "contact.list",
                "contact",
                details={"count": len(found), "searched": bool(query.text)},
            )
        )
        return [ContactDTO.from_domain(c) for c in found]


@dataclass(frozen=True)
class GetContactQuery:
    tenant_id: TenantId
    actor: Actor
    contact_id: UUID


class GetContact:
    def __init__(self, uow: ContactsUnitOfWork, audit: AuditLogger) -> None:
        self._uow, self._audit = uow, audit

    async def __call__(self, query: GetContactQuery) -> ContactDTO:
        async with self._uow as uow:
            contact = await uow.contacts.get(query.contact_id)
        await self._audit.record(
            AuditRecord(query.tenant_id, query.actor, "contact.read", "contact", query.contact_id)
        )
        return ContactDTO.from_domain(contact)
