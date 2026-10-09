"""/audit - mounted under /api. Admin only (permission audit.read)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.platform.audit.application.queries.list_entries import AuditFilter, ListAuditEntries
from app.shared.kernel.ids import TenantId
from app.shared.presentation.request_context import RequestContext, require

CanRead = Annotated[RequestContext, Depends(require("audit.read"))]


class AuditEntryResponse(BaseModel):
    id: UUID
    actor_kind: str
    actor_id: UUID | None
    action: str
    resource_type: str
    resource_id: UUID | None
    details: dict[str, Any]
    at: datetime


def build_router(for_tenant: Callable[[TenantId], ListAuditEntries]) -> APIRouter:
    router = APIRouter(prefix="/audit", tags=["audit"])

    @router.get("")
    async def list_entries(
        ctx: CanRead,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        actor_id: UUID | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[AuditEntryResponse]:
        entries = await for_tenant(ctx.tenant_id)(
            AuditFilter(resource_type, resource_id, actor_id, limit)
        )
        return [AuditEntryResponse(**vars(e)) for e in entries]

    return router
