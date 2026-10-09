from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.platform.tenancy.application.dto import LocationDTO
from app.platform.tenancy.application.unit_of_work import TenancyUnitOfWork
from app.platform.tenancy.domain.location import Location
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId


@dataclass(frozen=True)
class AddLocationCommand:
    tenant_id: TenantId
    name: str
    address: str
    actor: Actor
    timezone: str | None = None  # None: the tenant's timezone


class AddLocation:
    def __init__(self, uow: TenancyUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        self._uow, self._clock, self._ids = uow, clock, ids

    async def __call__(self, cmd: AddLocationCommand) -> LocationDTO:
        async with self._uow as uow:
            timezone = cmd.timezone or (await uow.tenants.get(cmd.tenant_id)).timezone
            location = Location.create(
                id=self._ids.new_id(),
                tenant_id=cmd.tenant_id,
                name=cmd.name,
                address=cmd.address,
                timezone=timezone,
                actor=cmd.actor,
                at=self._clock.now(),
            )
            await uow.locations.add(location)
            await uow.commit()
        return LocationDTO.from_domain(location)


@dataclass(frozen=True)
class UpdateLocationCommand:
    location_id: UUID
    actor: Actor
    name: str | None = None
    address: str | None = None
    timezone: str | None = None
    is_active: bool | None = None


class UpdateLocation:
    def __init__(self, uow: TenancyUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: UpdateLocationCommand) -> LocationDTO:
        async with self._uow as uow:
            location = await uow.locations.get(cmd.location_id)
            location.update(
                name=cmd.name,
                address=cmd.address,
                timezone=cmd.timezone,
                is_active=cmd.is_active,
                actor=cmd.actor,
                at=self._clock.now(),
            )
            await uow.locations.save(location)
            await uow.commit()
        return LocationDTO.from_domain(location)
