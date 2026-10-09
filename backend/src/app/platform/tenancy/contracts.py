"""Public surface of tenancy for other modules (ARCHITECTURE §3.3).

- `names(ids)`: tenant display names (satisfies identity's TenantDirectory port)
- `resolve_phone_number_id(id)`: webhook routing (conversation pipeline, step 3)
"""

from __future__ import annotations

from collections.abc import Collection

from app.platform.tenancy.application.dto import TenantRoute
from app.platform.tenancy.application.queries.tenants import (
    ResolveTenantByPhoneNumberId,
    TenantNames,
)
from app.shared.kernel.ids import TenantId

__all__ = ["TenancyFacade", "TenantRoute"]


class TenancyFacade:
    def __init__(self, names: TenantNames, resolver: ResolveTenantByPhoneNumberId) -> None:
        self._names, self._resolver = names, resolver

    async def names(self, tenant_ids: Collection[TenantId]) -> dict[TenantId, str]:
        return await self._names.names(tenant_ids)

    async def resolve_phone_number_id(self, phone_number_id: str) -> TenantRoute | None:
        return await self._resolver(phone_number_id)
