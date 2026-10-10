"""Public surface of tenancy for other modules (ARCHITECTURE §3.3). Framework-free: built by
tenancy's wiring with a Unit-of-Work factory, used through these methods only.

- names(ids)                      tenant display names (identity's TenantDirectory port)
- resolve_phone_number_id(id)     webhook routing (conversation pipeline)
- location_timezone(tenant, id)   a location's timezone (slot times are local wall-clock)
- module_settings(tenant, key)    a tenant's settings for one module (e.g. appointments policy)
- update_module_settings(...)     validated by the owning module before calling
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from typing import Any
from uuid import UUID

from app.platform.tenancy.application.commands.tenants import (
    UpdateModuleSettings,
    UpdateModuleSettingsCommand,
)
from app.platform.tenancy.application.dto import TenantRoute
from app.platform.tenancy.application.queries.tenants import (
    ResolveTenantByPhoneNumberId,
    TenantNames,
)
from app.platform.tenancy.application.unit_of_work import TenancyUnitOfWork
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import TenantId

__all__ = ["TenancyFacade", "TenantRoute"]


class TenancyFacade:
    def __init__(
        self, uow_for: Callable[[TenantId | None], TenancyUnitOfWork], clock: Clock
    ) -> None:
        self._uow_for, self._clock = uow_for, clock

    async def names(self, tenant_ids: Collection[TenantId]) -> dict[TenantId, str]:
        return await TenantNames(self._uow_for(None)).names(tenant_ids)

    async def resolve_phone_number_id(self, phone_number_id: str) -> TenantRoute | None:
        return await ResolveTenantByPhoneNumberId(self._uow_for(None))(phone_number_id)

    async def location_timezone(self, tenant_id: TenantId, location_id: UUID) -> str:
        async with self._uow_for(tenant_id) as uow:
            return (await uow.locations.get(location_id)).timezone

    async def module_settings(self, tenant_id: TenantId, module_key: str) -> dict[str, Any]:
        async with self._uow_for(tenant_id) as uow:
            return dict((await uow.tenants.get(tenant_id)).modules.get(module_key) or {})

    async def update_module_settings(
        self, tenant_id: TenantId, module_key: str, settings: dict[str, Any], actor: Actor
    ) -> None:
        await UpdateModuleSettings(self._uow_for(tenant_id), self._clock)(
            UpdateModuleSettingsCommand(tenant_id, module_key, settings, actor)
        )
