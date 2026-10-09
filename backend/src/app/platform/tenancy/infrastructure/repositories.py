from __future__ import annotations

from collections.abc import Collection
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, RowMapping, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.tenancy.domain.errors import (
    LocationNotFoundError,
    PhoneNumberIdTakenError,
    SlugTakenError,
    TenantNotFoundError,
)
from app.platform.tenancy.domain.location import Location
from app.platform.tenancy.domain.tenant import Tenant, TenantStatus
from app.platform.tenancy.domain.whatsapp_number import WhatsAppNumber
from app.platform.tenancy.infrastructure.tables import locations, tenants, whatsapp_numbers
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.kernel.errors import ConcurrencyConflictError
from app.shared.kernel.ids import TenantId


async def _versioned_update(
    session: AsyncSession, table: Any, entity_id: UUID, version: int, values: dict[str, Any]
) -> None:
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(table)
            .where(table.c.id == entity_id, table.c.version == version)
            .values(values | {"version": version + 1})
        ),
    )
    if result.rowcount != 1:
        raise ConcurrencyConflictError()


# ---------------------------------------------------------------- tenants
def _tenant(row: RowMapping) -> Tenant:
    return Tenant(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        timezone=row["timezone"],
        status=TenantStatus(row["status"]),
        modules=dict(row["modules"]),
        created_at=row["created_at"],
        version=row["version"],
    )


def _tenant_row(t: Tenant) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "timezone": t.timezone,
        "status": t.status.value,
        "modules": t.modules,
        "created_at": t.created_at,
        "version": t.version,
    }


class SqlTenantRepository:
    def __init__(self, session: AsyncSession, uow: UnitOfWork) -> None:
        self._session, self._uow = session, uow

    async def get(self, tenant_id: TenantId) -> Tenant:
        row = (
            (await self._session.execute(select(tenants).where(tenants.c.id == tenant_id)))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise TenantNotFoundError()
        tenant = _tenant(row)
        self._uow.track(tenant)
        return tenant

    async def list_all(self) -> list[Tenant]:
        rows = (await self._session.execute(select(tenants).order_by(tenants.c.name))).mappings()
        return [_tenant(r) for r in rows]

    async def names(self, tenant_ids: Collection[TenantId]) -> dict[TenantId, str]:
        rows = await self._session.execute(
            select(tenants.c.id, tenants.c.name).where(tenants.c.id.in_(list(tenant_ids)))
        )
        return {TenantId(r.id): r.name for r in rows}

    async def add(self, tenant: Tenant) -> None:
        try:
            async with self._session.begin_nested():
                await self._session.execute(insert(tenants).values(_tenant_row(tenant)))
        except IntegrityError as exc:
            raise SlugTakenError(f"Slug {tenant.slug!r} is already used") from exc
        self._uow.track(tenant)

    async def save(self, tenant: Tenant) -> None:
        await _versioned_update(
            self._session, tenants, tenant.id, tenant.version, _tenant_row(tenant)
        )
        tenant.version += 1
        self._uow.track(tenant)


# ---------------------------------------------------------------- locations (RLS)
def _location(row: RowMapping) -> Location:
    return Location(
        id=row["id"],
        tenant_id=TenantId(row["tenant_id"]),
        name=row["name"],
        address=row["address"],
        timezone=row["timezone"],
        is_active=row["is_active"],
        created_at=row["created_at"],
        version=row["version"],
    )


def _location_row(loc: Location) -> dict[str, Any]:
    return {
        "id": loc.id,
        "tenant_id": loc.tenant_id,
        "name": loc.name,
        "address": loc.address,
        "timezone": loc.timezone,
        "is_active": loc.is_active,
        "created_at": loc.created_at,
        "version": loc.version,
    }


class SqlLocationRepository:
    def __init__(self, session: AsyncSession, uow: UnitOfWork) -> None:
        self._session, self._uow = session, uow

    async def get(self, location_id: UUID) -> Location:
        row = (
            (await self._session.execute(select(locations).where(locations.c.id == location_id)))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise LocationNotFoundError()
        location = _location(row)
        self._uow.track(location)
        return location

    async def list(self) -> list[Location]:
        return [_location(r) for r in (await self._session.execute(select(locations))).mappings()]

    async def add(self, location: Location) -> None:
        await self._session.execute(insert(locations).values(_location_row(location)))
        self._uow.track(location)

    async def save(self, location: Location) -> None:
        await _versioned_update(
            self._session, locations, location.id, location.version, _location_row(location)
        )
        location.version += 1
        self._uow.track(location)


# ---------------------------------------------------------------- whatsapp numbers
def _number(row: RowMapping) -> WhatsAppNumber:
    return WhatsAppNumber(
        id=row["id"],
        tenant_id=TenantId(row["tenant_id"]),
        phone_number_id=row["phone_number_id"],
        display_phone=row["display_phone"],
        is_active=row["is_active"],
        connected_at=row["connected_at"],
    )


class SqlWhatsAppNumberRepository:
    def __init__(self, session: AsyncSession, uow: UnitOfWork) -> None:
        self._session, self._uow = session, uow

    async def find_by_phone_number_id(self, phone_number_id: str) -> WhatsAppNumber | None:
        row = (
            (
                await self._session.execute(
                    select(whatsapp_numbers).where(
                        whatsapp_numbers.c.phone_number_id == phone_number_id
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return _number(row) if row else None

    async def list_for_tenant(self, tenant_id: TenantId) -> list[WhatsAppNumber]:
        rows = await self._session.execute(
            select(whatsapp_numbers).where(whatsapp_numbers.c.tenant_id == tenant_id)
        )
        return [_number(r) for r in rows.mappings()]

    async def add(self, number: WhatsAppNumber) -> None:
        try:
            async with self._session.begin_nested():
                await self._session.execute(
                    insert(whatsapp_numbers).values(
                        id=number.id,
                        tenant_id=number.tenant_id,
                        phone_number_id=number.phone_number_id,
                        display_phone=number.display_phone,
                        is_active=number.is_active,
                        connected_at=number.connected_at,
                    )
                )
        except IntegrityError as exc:
            raise PhoneNumberIdTakenError() from exc
        self._uow.track(number)
