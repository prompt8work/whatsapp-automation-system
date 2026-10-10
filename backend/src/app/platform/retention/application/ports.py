from __future__ import annotations

from typing import Protocol

from app.platform.retention.domain.record import DeletionRecord
from app.shared.kernel.ids import TenantId


class TenantList(Protocol):
    async def all_tenant_ids(self) -> list[TenantId]: ...


class DeletionRecords(Protocol):
    """Append-only (PRD AP-10.5)."""

    async def add(self, record: DeletionRecord) -> None: ...

    async def list(self, tenant_id: TenantId, limit: int) -> list[DeletionRecord]:
        """Newest first."""
        ...
