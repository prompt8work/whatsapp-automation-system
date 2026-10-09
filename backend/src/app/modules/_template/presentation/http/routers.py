"""HTTP routes. Thin: parse request -> build command -> call use case -> map response.

No business rules here. Domain errors bubble up and are mapped to HTTP statuses by
the shared error handler using HTTP_ERROR_STATUS.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.modules._template.application.commands.create_item import CreateItemCommand
from app.modules._template.application.commands.rename_item import RenameItemCommand
from app.modules._template.application.queries.get_item import GetItemQuery
from app.modules._template.application.use_cases import ItemUseCases
from app.modules._template.presentation.http.schemas import (
    CreateItemRequest,
    ItemResponse,
    RenameItemRequest,
)
from app.shared.kernel.ids import TenantId
from app.shared.presentation.request_context import RequestContext, require

HTTP_ERROR_STATUS = {
    "template.item_not_found": status.HTTP_404_NOT_FOUND,
    "template.invalid_name": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "template.name_unchanged": status.HTTP_409_CONFLICT,
}

CanRead = Annotated[RequestContext, Depends(require("template.item.read"))]
CanWrite = Annotated[RequestContext, Depends(require("template.item.write"))]


def build_router(use_cases_for: Callable[[TenantId], ItemUseCases]) -> APIRouter:
    router = APIRouter(prefix="/template/items", tags=["_template"])

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def create_item(body: CreateItemRequest, ctx: CanWrite) -> ItemResponse:
        dto = await use_cases_for(ctx.tenant_id).create(
            CreateItemCommand(name=body.name, actor=ctx.actor)
        )
        return ItemResponse.from_dto(dto)

    @router.get("/{item_id}")
    async def get_item(item_id: UUID, ctx: CanRead) -> ItemResponse:
        dto = await use_cases_for(ctx.tenant_id).get(GetItemQuery(item_id=item_id))
        return ItemResponse.from_dto(dto)

    @router.patch("/{item_id}")
    async def rename_item(item_id: UUID, body: RenameItemRequest, ctx: CanWrite) -> ItemResponse:
        dto = await use_cases_for(ctx.tenant_id).rename(
            RenameItemCommand(item_id=item_id, new_name=body.name, actor=ctx.actor)
        )
        return ItemResponse.from_dto(dto)

    return router
