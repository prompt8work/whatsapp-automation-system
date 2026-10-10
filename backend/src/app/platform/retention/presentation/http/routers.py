"""/retention - mounted under /api. What was deleted, and what will be soon (AP-10.5, 10.6)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.platform.retention.application.use_cases import ListDeletionRecords, Upcoming
from app.shared.presentation.request_context import RequestContext, require

CanRead = Annotated[RequestContext, Depends(require("retention.read"))]


class DeletionRecordResponse(BaseModel):
    id: UUID
    purger: str
    subject_type: str
    subject_id: UUID
    rule: str
    counts: dict[str, int]
    at: datetime


class UpcomingDeletionResponse(BaseModel):
    purger: str
    subject_type: str
    subject_id: UUID
    rule: str
    due_at: datetime
    label: str


def build_router(records: ListDeletionRecords, upcoming: Upcoming) -> APIRouter:
    router = APIRouter(prefix="/retention", tags=["retention"])

    @router.get("/records")
    async def list_records(
        ctx: CanRead, limit: Annotated[int, Query(ge=1, le=500)] = 200
    ) -> list[DeletionRecordResponse]:
        return [
            DeletionRecordResponse(
                id=r.id,
                purger=r.purger,
                subject_type=r.subject_type,
                subject_id=r.subject_id,
                rule=r.rule,
                counts=r.counts,
                at=r.at or datetime.min,
            )
            for r in await records(ctx.tenant_id, limit)
        ]

    @router.get("/upcoming")
    async def list_upcoming(ctx: CanRead) -> list[UpcomingDeletionResponse]:
        return [
            UpcomingDeletionResponse(
                purger=u.purger,
                subject_type=u.target.subject_type,
                subject_id=u.target.subject_id,
                rule=u.target.rule,
                due_at=u.target.due_at,
                label=u.target.label,
            )
            for u in await upcoming(ctx.tenant_id)
        ]

    return router
