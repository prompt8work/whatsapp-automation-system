from __future__ import annotations

from collections.abc import Collection

from app.platform.tenancy.application.dto import (
    LocationDTO,
    TenantDTO,
    TenantRoute,
    WhatsAppNumberDTO,
)
from app.platform.tenancy.application.unit_of_work import TenancyUnitOfWork
from app.shared.kernel.ids import TenantId


class ListTenants:
    def __init__(self, uow: TenancyUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self) -> list[TenantDTO]:
        async with self._uow as uow:
            return [TenantDTO.from_domain(t) for t in await uow.tenants.list_all()]


class GetTenant:
    def __init__(self, uow: TenancyUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, tenant_id: TenantId) -> TenantDTO:
        async with self._uow as uow:
            return TenantDTO.from_domain(await uow.tenants.get(tenant_id))


class TenantNames:
    """Satisfies identity's TenantDirectory port (wired by bootstrap)."""

    def __init__(self, uow: TenancyUnitOfWork) -> None:
        self._uow = uow

    async def names(self, tenant_ids: Collection[TenantId]) -> dict[TenantId, str]:
        if not tenant_ids:
            return {}
        async with self._uow as uow:
            return await uow.tenants.names(tenant_ids)


class ResolveTenantByPhoneNumberId:
    """Webhook routing: Meta phone_number_id -> active tenant. None = ignore the webhook."""

    def __init__(self, uow: TenancyUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, phone_number_id: str) -> TenantRoute | None:
        async with self._uow as uow:
            number = await uow.whatsapp_numbers.find_by_phone_number_id(phone_number_id)
            if number is None or not number.is_active:
                return None
            tenant = await uow.tenants.get(number.tenant_id)
            if not tenant.is_active:
                return None
        return TenantRoute(
            tenant_id=TenantId(tenant.id),
            whatsapp_number_id=number.id,
            timezone=tenant.timezone,
            enabled_modules=frozenset(tenant.modules),
        )


class ListLocations:
    def __init__(self, uow: TenancyUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self) -> list[LocationDTO]:
        async with self._uow as uow:
            locations = await uow.locations.list()
        return [LocationDTO.from_domain(loc) for loc in sorted(locations, key=lambda x: x.name)]


class ListWhatsAppNumbers:
    def __init__(self, uow: TenancyUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, tenant_id: TenantId) -> list[WhatsAppNumberDTO]:
        async with self._uow as uow:
            numbers = await uow.whatsapp_numbers.list_for_tenant(tenant_id)
        return [WhatsAppNumberDTO.from_domain(n) for n in numbers]
