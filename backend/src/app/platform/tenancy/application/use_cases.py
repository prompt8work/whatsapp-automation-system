"""Two bundles because they run with different Unit-of-Work scopes:

- PlatformTenancyUseCases: super-admin, NO tenant set (tenants / numbers are platform tables)
- TenantTenancyUseCases:   one tenant's admin/staff, tenant set (locations are RLS-protected)
"""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class PlatformTenancyUseCases:
    create_tenant: CreateTenant
    list_tenants: ListTenants
    set_status: SetTenantStatus
    set_module: SetModuleEnabled
    connect_whatsapp_number: ConnectWhatsAppNumber
    list_whatsapp_numbers: ListWhatsAppNumbers


@dataclass(frozen=True)
class TenantTenancyUseCases:
    get_tenant: GetTenant
    update_tenant: UpdateTenant
    update_module_settings: UpdateModuleSettings
    list_locations: ListLocations
    add_location: AddLocation
    update_location: UpdateLocation
