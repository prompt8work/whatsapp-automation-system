"""A clinic branch: own address, own timezone, own QR code (PRD PL-1.5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.platform.tenancy.domain.events import LocationAdded, LocationUpdated
from app.platform.tenancy.domain.values import valid_name, valid_timezone
from app.shared.kernel.actor import Actor
from app.shared.kernel.entity import TenantAggregateRoot
from app.shared.kernel.ids import TenantId


@dataclass(kw_only=True, eq=False)
class Location(TenantAggregateRoot):
    name: str
    address: str
    timezone: str
    created_at: datetime
    is_active: bool = True

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: TenantId,
        name: str,
        address: str,
        timezone: str,
        actor: Actor,
        at: datetime,
    ) -> Location:
        location = cls(
            id=id,
            tenant_id=tenant_id,
            name=valid_name(name),
            address=address.strip(),
            timezone=valid_timezone(timezone),
            created_at=at,
        )
        location.record(LocationAdded(occurred_at=at, location_id=id, actor=actor))
        return location

    def update(
        self,
        *,
        name: str | None = None,
        address: str | None = None,
        timezone: str | None = None,
        is_active: bool | None = None,
        actor: Actor,
        at: datetime,
    ) -> None:
        if name is not None:
            self.name = valid_name(name)
        if address is not None:
            self.address = address.strip()
        if timezone is not None:
            self.timezone = valid_timezone(timezone)
        if is_active is not None:
            self.is_active = is_active
        self.record(LocationUpdated(occurred_at=at, location_id=self.id, actor=actor))
