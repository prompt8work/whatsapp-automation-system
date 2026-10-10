"""handovers table (tenant-owned, RLS) + repository + Unit of Work."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    RowMapping,
    String,
    Table,
    Uuid,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert

from app.platform.inbox.domain.handover import Handover
from app.shared.infrastructure.tables import metadata
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork
from app.shared.kernel.ids import TenantId

handovers = Table(
    "handovers",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("contact_id", Uuid, nullable=False),
    Column("reason", String(20), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("assigned_user_id", Uuid, nullable=True),
    Column("ended_at", DateTime(timezone=True), nullable=True),
    Column("version", Integer, nullable=False),
    # At most one ACTIVE handover per contact.
    Index(
        "uq_handovers_active_contact",
        "contact_id",
        unique=True,
        postgresql_where=text("ended_at IS NULL"),
    ),
)


def _handover(r: RowMapping) -> Handover:
    return Handover(
        id=r["id"],
        tenant_id=TenantId(r["tenant_id"]),
        contact_id=r["contact_id"],
        reason=r["reason"],
        started_at=r["started_at"],
        assigned_user_id=r["assigned_user_id"],
        ended_at=r["ended_at"],
        version=r["version"],
    )


def _row(h: Handover) -> dict[str, Any]:
    return {
        "id": h.id,
        "tenant_id": h.tenant_id,
        "contact_id": h.contact_id,
        "reason": h.reason,
        "started_at": h.started_at,
        "assigned_user_id": h.assigned_user_id,
        "ended_at": h.ended_at,
        "version": h.version,
    }


class SqlHandoverRepository:
    def __init__(self, uow: SqlUnitOfWork) -> None:
        self._uow = uow

    async def active_for(self, contact_id: UUID) -> Handover | None:
        row = (
            (
                await self._uow.session.execute(
                    select(handovers).where(
                        handovers.c.contact_id == contact_id, handovers.c.ended_at.is_(None)
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        handover = _handover(row)
        self._uow.track(handover)
        return handover

    async def all_active(self) -> list[Handover]:
        rows = await self._uow.session.execute(
            select(handovers).where(handovers.c.ended_at.is_(None))
        )
        return [_handover(r) for r in rows.mappings()]

    async def add(self, handover: Handover) -> bool:
        result = await self._uow.session.execute(
            insert(handovers)
            .values(_row(handover))
            .on_conflict_do_nothing(
                index_elements=["contact_id"], index_where=handovers.c.ended_at.is_(None)
            )
            .returning(handovers.c.id)
        )
        if result.scalar_one_or_none() is None:
            return False
        self._uow.track(handover)
        return True

    async def save(self, handover: Handover) -> None:
        await self._uow.session.execute(
            update(handovers)
            .where(handovers.c.id == handover.id)
            .values(_row(handover) | {"version": handover.version + 1})
        )
        handover.version += 1
        self._uow.track(handover)


class SqlInboxUnitOfWork(SqlUnitOfWork):
    handovers: SqlHandoverRepository

    def _create_repositories(self) -> None:
        self.handovers = SqlHandoverRepository(self)
