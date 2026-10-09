"""Tenant lifecycle. Create / status / modules: platform super-admin. Update / module
settings: the tenant's own admin (permission tenant.settings.manage)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.platform.tenancy.application.dto import TenantDTO
from app.platform.tenancy.application.unit_of_work import TenancyUnitOfWork
from app.platform.tenancy.domain.tenant import Tenant, TenantStatus
from app.platform.tenancy.domain.values import DEFAULT_TIMEZONE
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId


@dataclass(frozen=True)
class CreateTenantCommand:
    name: str
    slug: str
    actor: Actor
    timezone: str = DEFAULT_TIMEZONE
    modules: tuple[str, ...] = ()


class CreateTenant:
    def __init__(self, uow: TenancyUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        self._uow, self._clock, self._ids = uow, clock, ids

    async def __call__(self, cmd: CreateTenantCommand) -> TenantDTO:
        now = self._clock.now()
        tenant = Tenant.create(
            id=self._ids.new_id(),
            name=cmd.name,
            slug=cmd.slug,
            timezone=cmd.timezone,
            actor=cmd.actor,
            at=now,
        )
        for key in cmd.modules:
            tenant.enable_module(key, actor=cmd.actor, at=now)
        async with self._uow as uow:
            await uow.tenants.add(tenant)
            await uow.commit()
        return TenantDTO.from_domain(tenant)


@dataclass(frozen=True)
class UpdateTenantCommand:
    tenant_id: TenantId
    actor: Actor
    name: str | None = None
    timezone: str | None = None


class UpdateTenant:
    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: UpdateTenantCommand) -> TenantDTO:
        async with self._uow as uow:
            tenant = await uow.tenants.get(cmd.tenant_id)
            tenant.update(
                name=cmd.name, timezone=cmd.timezone, actor=cmd.actor, at=self._clock.now()
            )
            await uow.tenants.save(tenant)
            await uow.commit()
        return TenantDTO.from_domain(tenant)


@dataclass(frozen=True)
class SetTenantStatusCommand:
    tenant_id: TenantId
    status: TenantStatus
    actor: Actor


class SetTenantStatus:
    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: SetTenantStatusCommand) -> TenantDTO:
        async with self._uow as uow:
            tenant = await uow.tenants.get(cmd.tenant_id)
            tenant.set_status(cmd.status, actor=cmd.actor, at=self._clock.now())
            await uow.tenants.save(tenant)
            await uow.commit()
        return TenantDTO.from_domain(tenant)


@dataclass(frozen=True)
class SetModuleCommand:
    tenant_id: TenantId
    module_key: str
    enabled: bool
    actor: Actor


class SetModuleEnabled:
    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: SetModuleCommand) -> TenantDTO:
        now = self._clock.now()
        async with self._uow as uow:
            tenant = await uow.tenants.get(cmd.tenant_id)
            if cmd.enabled:
                tenant.enable_module(cmd.module_key, actor=cmd.actor, at=now)
            else:
                tenant.disable_module(cmd.module_key, actor=cmd.actor, at=now)
            await uow.tenants.save(tenant)
            await uow.commit()
        return TenantDTO.from_domain(tenant)


@dataclass(frozen=True)
class UpdateModuleSettingsCommand:
    tenant_id: TenantId
    module_key: str
    settings: dict[str, Any]
    actor: Actor


class UpdateModuleSettings:
    """Settings are validated by the owning module's schema at the HTTP edge (step 4+)."""

    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: UpdateModuleSettingsCommand) -> TenantDTO:
        async with self._uow as uow:
            tenant = await uow.tenants.get(cmd.tenant_id)
            tenant.update_module_settings(
                cmd.module_key, cmd.settings, actor=cmd.actor, at=self._clock.now()
            )
            await uow.tenants.save(tenant)
            await uow.commit()
        return TenantDTO.from_domain(tenant)
