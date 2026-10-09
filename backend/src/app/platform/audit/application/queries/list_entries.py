from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.platform.audit.domain.entry import AuditEntry


@dataclass(frozen=True)
class AuditFilter:
    resource_type: str | None = None
    resource_id: UUID | None = None
    actor_id: UUID | None = None
    limit: int = 100


class AuditReadModel(Protocol):
    """Tenant-scoped (RLS): returns the current tenant's entries only, newest first."""

    async def list(self, query: AuditFilter) -> list[AuditEntry]: ...


class ListAuditEntries:
    def __init__(self, read_model: AuditReadModel) -> None:
        self._read_model = read_model

    async def __call__(self, query: AuditFilter) -> list[AuditEntry]:
        return await self._read_model.list(query)
