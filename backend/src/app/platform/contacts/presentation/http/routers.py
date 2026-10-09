"""/contacts - mounted under /api by the app factory."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from app.platform.contacts.application.commands.preferences import SetOptOutCommand
from app.platform.contacts.application.dto import ContactDTO
from app.platform.contacts.application.queries.contacts import (
    MAX_PAGE_SIZE,
    GetContactQuery,
    SearchContactsQuery,
)
from app.platform.contacts.application.use_cases import ContactsUseCases
from app.shared.kernel.ids import TenantId
from app.shared.presentation.request_context import RequestContext, require

HTTP_ERROR_STATUS = {
    "contacts.not_found": status.HTTP_404_NOT_FOUND,
    "contacts.invalid_phone": status.HTTP_422_UNPROCESSABLE_CONTENT,
}

CanRead = Annotated[RequestContext, Depends(require("contact.read"))]
CanManage = Annotated[RequestContext, Depends(require("contact.manage"))]


class ContactResponse(BaseModel):
    id: UUID
    phone: str
    profile_name: str | None
    first_seen_at: datetime
    last_inbound_at: datetime | None
    has_consent: bool
    is_opted_out: bool

    @classmethod
    def from_dto(cls, c: ContactDTO) -> ContactResponse:
        return cls(
            id=c.id,
            phone=c.phone,
            profile_name=c.profile_name,
            first_seen_at=c.first_seen_at,
            last_inbound_at=c.last_inbound_at,
            has_consent=c.has_consent,
            is_opted_out=c.is_opted_out,
        )


class OptOutRequest(BaseModel):
    opted_out: bool


def build_router(for_tenant: Callable[[TenantId], ContactsUseCases]) -> APIRouter:
    router = APIRouter(prefix="/contacts", tags=["contacts"])

    @router.get("")
    async def search_contacts(
        ctx: CanRead,
        q: Annotated[str | None, Query(max_length=100)] = None,
        limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[ContactResponse]:
        found = await for_tenant(ctx.tenant_id).search(
            SearchContactsQuery(ctx.tenant_id, ctx.actor, text=q, limit=limit, offset=offset)
        )
        return [ContactResponse.from_dto(c) for c in found]

    @router.get("/{contact_id}")
    async def get_contact(contact_id: UUID, ctx: CanRead) -> ContactResponse:
        contact = await for_tenant(ctx.tenant_id).get(
            GetContactQuery(ctx.tenant_id, ctx.actor, contact_id)
        )
        return ContactResponse.from_dto(contact)

    @router.put("/{contact_id}/opt-out")
    async def set_opt_out(contact_id: UUID, body: OptOutRequest, ctx: CanManage) -> ContactResponse:
        contact = await for_tenant(ctx.tenant_id).set_opt_out(
            SetOptOutCommand(ctx.tenant_id, contact_id, body.opted_out, ctx.actor)
        )
        return ContactResponse.from_dto(contact)

    return router
