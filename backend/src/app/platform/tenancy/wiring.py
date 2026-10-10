from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter

from app.platform.tenancy.application.commands.connect_whatsapp_number import (
    ConnectWhatsAppNumber,
)
from app.platform.tenancy.application.commands.locations import AddLocation, UpdateLocation
from app.platform.tenancy.application.commands.tenants import (
    CreateTenant,
    SetModuleEnabled,
    SetTenantStatus,
    UpdateModuleSettings,
    UpdateTenant,
)
from app.platform.tenancy.application.queries.tenants import (
    GetTenant,
    ListLocations,
    ListTenants,
    ListWhatsAppNumbers,
)
from app.platform.tenancy.application.use_cases import (
    PlatformTenancyUseCases,
    TenantTenancyUseCases,
)
from app.platform.tenancy.contracts import TenancyFacade
from app.platform.tenancy.infrastructure.unit_of_work import SqlTenancyUnitOfWork
from app.platform.tenancy.presentation.http.routers import build_routers as build_http_routers
from app.shared.kernel.ids import TenantId
from app.shared.module import PlatformServices


def build_routers(services: PlatformServices) -> Sequence[APIRouter]:
    clock, ids = services.clock, services.ids
    platform_uow = SqlTenancyUnitOfWork(services.session_factory, tenant_id=None)
    platform = PlatformTenancyUseCases(
        create_tenant=CreateTenant(platform_uow, clock, ids),
        list_tenants=ListTenants(platform_uow),
        set_status=SetTenantStatus(platform_uow, clock),
        set_module=SetModuleEnabled(platform_uow, clock),
        connect_whatsapp_number=ConnectWhatsAppNumber(platform_uow, clock, ids),
        list_whatsapp_numbers=ListWhatsAppNumbers(platform_uow),
    )

    def for_tenant(tenant_id: TenantId) -> TenantTenancyUseCases:
        uow = SqlTenancyUnitOfWork(services.session_factory, tenant_id)
        return TenantTenancyUseCases(
            get_tenant=GetTenant(uow),
            update_tenant=UpdateTenant(uow, clock),
            update_module_settings=UpdateModuleSettings(uow, clock),
            list_locations=ListLocations(uow),
            add_location=AddLocation(uow, clock, ids),
            update_location=UpdateLocation(uow, clock),
        )

    return build_http_routers(platform, for_tenant)


def build_facade(services: PlatformServices) -> TenancyFacade:
    return TenancyFacade(
        lambda tenant_id: SqlTenancyUnitOfWork(services.session_factory, tenant_id), services.clock
    )
