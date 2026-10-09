"""/platform/tenants/* (super-admin) and /tenant, /locations (the tenant's own).
Mounted under /api by the app factory."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, status

from app.platform.tenancy.application.commands.connect_whatsapp_number import (
    ConnectWhatsAppNumberCommand,
)
from app.platform.tenancy.application.commands.locations import (
    AddLocationCommand,
    UpdateLocationCommand,
)
from app.platform.tenancy.application.commands.tenants import (
    CreateTenantCommand,
    SetModuleCommand,
    SetTenantStatusCommand,
    UpdateModuleSettingsCommand,
    UpdateTenantCommand,
)
from app.platform.tenancy.application.use_cases import (
    PlatformTenancyUseCases,
    TenantTenancyUseCases,
)
from app.platform.tenancy.domain.tenant import TenantStatus
from app.platform.tenancy.presentation.http.schemas import (
    ConnectNumberRequest,
    CreateTenantRequest,
    LocationRequest,
    LocationResponse,
    TenantResponse,
    TenantStatusRequest,
    UpdateLocationRequest,
    UpdateTenantRequest,
    WhatsAppNumberResponse,
)
from app.shared.application.auth import Principal
from app.shared.kernel.ids import TenantId
from app.shared.presentation.request_context import (
    RequestContext,
    get_request_context,
    require,
    require_super_admin,
)

HTTP_ERROR_STATUS = {
    "tenancy.tenant_not_found": status.HTTP_404_NOT_FOUND,
    "tenancy.location_not_found": status.HTTP_404_NOT_FOUND,
    "tenancy.invalid_slug": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "tenancy.invalid_timezone": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "tenancy.invalid_name": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "tenancy.invalid_phone_number_id": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "tenancy.slug_taken": status.HTTP_409_CONFLICT,
    "tenancy.phone_number_id_taken": status.HTTP_409_CONFLICT,
    "tenancy.module_not_enabled": status.HTTP_409_CONFLICT,
}

SuperAdmin = Annotated[Principal, Depends(require_super_admin)]
Member = Annotated[RequestContext, Depends(get_request_context)]
CanManageSettings = Annotated[RequestContext, Depends(require("tenant.settings.manage"))]
CanReadLocations = Annotated[RequestContext, Depends(require("locations.read"))]
CanManageLocations = Annotated[RequestContext, Depends(require("locations.manage"))]


def build_routers(
    platform: PlatformTenancyUseCases,
    for_tenant: Callable[[TenantId], TenantTenancyUseCases],
) -> list[APIRouter]:
    admin = APIRouter(prefix="/platform/tenants", tags=["platform"])
    own = APIRouter(tags=["tenant"])

    # ------------------------------------------------------------- super-admin
    @admin.get("")
    async def list_tenants(_: SuperAdmin) -> list[TenantResponse]:
        return [TenantResponse.from_dto(t) for t in await platform.list_tenants()]

    @admin.post("", status_code=status.HTTP_201_CREATED)
    async def create_tenant(body: CreateTenantRequest, sa: SuperAdmin) -> TenantResponse:
        tenant = await platform.create_tenant(
            CreateTenantCommand(
                name=body.name,
                slug=body.slug,
                timezone=body.timezone,
                modules=tuple(body.modules),
                actor=sa.actor,
            )
        )
        return TenantResponse.from_dto(tenant)

    @admin.put("/{tenant_id}/status")
    async def set_status(
        tenant_id: UUID, body: TenantStatusRequest, sa: SuperAdmin
    ) -> TenantResponse:
        tenant = await platform.set_status(
            SetTenantStatusCommand(TenantId(tenant_id), TenantStatus(body.status), sa.actor)
        )
        return TenantResponse.from_dto(tenant)

    @admin.put("/{tenant_id}/modules/{module_key}")
    async def enable_module(tenant_id: UUID, module_key: str, sa: SuperAdmin) -> TenantResponse:
        cmd = SetModuleCommand(TenantId(tenant_id), module_key, enabled=True, actor=sa.actor)
        return TenantResponse.from_dto(await platform.set_module(cmd))

    @admin.delete("/{tenant_id}/modules/{module_key}")
    async def disable_module(tenant_id: UUID, module_key: str, sa: SuperAdmin) -> TenantResponse:
        cmd = SetModuleCommand(TenantId(tenant_id), module_key, enabled=False, actor=sa.actor)
        return TenantResponse.from_dto(await platform.set_module(cmd))

    @admin.get("/{tenant_id}/whatsapp-numbers")
    async def list_numbers(tenant_id: UUID, _: SuperAdmin) -> list[WhatsAppNumberResponse]:
        numbers = await platform.list_whatsapp_numbers(TenantId(tenant_id))
        return [WhatsAppNumberResponse.from_dto(n) for n in numbers]

    @admin.post("/{tenant_id}/whatsapp-numbers", status_code=status.HTTP_201_CREATED)
    async def connect_number(
        tenant_id: UUID, body: ConnectNumberRequest, sa: SuperAdmin
    ) -> WhatsAppNumberResponse:
        number = await platform.connect_whatsapp_number(
            ConnectWhatsAppNumberCommand(
                tenant_id=TenantId(tenant_id),
                phone_number_id=body.phone_number_id,
                display_phone=body.display_phone,
                actor=sa.actor,
            )
        )
        return WhatsAppNumberResponse.from_dto(number)

    # ------------------------------------------------------------- own tenant
    @own.get("/tenant")
    async def get_tenant(ctx: Member) -> TenantResponse:
        return TenantResponse.from_dto(await for_tenant(ctx.tenant_id).get_tenant(ctx.tenant_id))

    @own.patch("/tenant")
    async def update_tenant(body: UpdateTenantRequest, ctx: CanManageSettings) -> TenantResponse:
        tenant = await for_tenant(ctx.tenant_id).update_tenant(
            UpdateTenantCommand(ctx.tenant_id, ctx.actor, name=body.name, timezone=body.timezone)
        )
        return TenantResponse.from_dto(tenant)

    @own.put("/tenant/modules/{module_key}/settings")
    async def update_module_settings(
        module_key: str, settings: Annotated[dict[str, Any], Body()], ctx: CanManageSettings
    ) -> TenantResponse:
        tenant = await for_tenant(ctx.tenant_id).update_module_settings(
            UpdateModuleSettingsCommand(ctx.tenant_id, module_key, settings, ctx.actor)
        )
        return TenantResponse.from_dto(tenant)

    @own.get("/locations")
    async def list_locations(ctx: CanReadLocations) -> list[LocationResponse]:
        return [
            LocationResponse.from_dto(x) for x in await for_tenant(ctx.tenant_id).list_locations()
        ]

    @own.post("/locations", status_code=status.HTTP_201_CREATED)
    async def add_location(body: LocationRequest, ctx: CanManageLocations) -> LocationResponse:
        location = await for_tenant(ctx.tenant_id).add_location(
            AddLocationCommand(
                tenant_id=ctx.tenant_id,
                name=body.name,
                address=body.address,
                timezone=body.timezone,
                actor=ctx.actor,
            )
        )
        return LocationResponse.from_dto(location)

    @own.patch("/locations/{location_id}")
    async def update_location(
        location_id: UUID, body: UpdateLocationRequest, ctx: CanManageLocations
    ) -> LocationResponse:
        location = await for_tenant(ctx.tenant_id).update_location(
            UpdateLocationCommand(
                location_id=location_id,
                actor=ctx.actor,
                name=body.name,
                address=body.address,
                timezone=body.timezone,
                is_active=body.is_active,
            )
        )
        return LocationResponse.from_dto(location)

    return [admin, own]
