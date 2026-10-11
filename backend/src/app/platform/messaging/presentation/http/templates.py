"""/templates - mounted under /api. Admins map each TemplateSlot to an approved template."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.platform.messaging.application.commands.templates import TemplateSettings
from app.shared.kernel.ids import TenantId
from app.shared.presentation.request_context import RequestContext, require

CanManage = Annotated[RequestContext, Depends(require("templates.manage"))]


class TemplateSlotResponse(BaseModel):
    slot: str
    description: str
    params: list[str]
    buttons: list[str]
    example: str
    template_name: str | None
    language: str | None


class MapTemplateRequest(BaseModel):
    template_name: str = Field(default="", max_length=512)  # empty = remove
    language: str = Field(default="en", max_length=10)


def build_router(for_tenant: Callable[[TenantId], TemplateSettings]) -> APIRouter:
    router = APIRouter(prefix="/templates", tags=["templates"])

    @router.get("")
    async def list_templates(ctx: CanManage) -> list[TemplateSlotResponse]:
        return [
            TemplateSlotResponse(
                slot=v.slot.key,
                description=v.slot.description,
                params=list(v.slot.params),
                buttons=list(v.slot.buttons),
                example=v.slot.example,
                template_name=v.mapping.name if v.mapping else None,
                language=v.mapping.language if v.mapping else None,
            )
            for v in await for_tenant(ctx.tenant_id).list()
        ]

    @router.put("/{slot}", status_code=status.HTTP_204_NO_CONTENT)
    async def map_template(slot: str, body: MapTemplateRequest, ctx: CanManage) -> None:
        await for_tenant(ctx.tenant_id).set(
            ctx.tenant_id, slot, body.template_name or None, body.language, ctx.actor
        )

    return router
