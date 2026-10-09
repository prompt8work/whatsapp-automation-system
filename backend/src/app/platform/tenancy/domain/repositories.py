from __future__ import annotations

from collections.abc import Collection
from typing import Protocol
from uuid import UUID

from app.platform.tenancy.domain.location import Location
from app.platform.tenancy.domain.tenant import Tenant
from app.platform.tenancy.domain.whatsapp_number import WhatsAppNumber
from app.shared.kernel.ids import TenantId


class TenantRepository(Protocol):
    async def get(self, tenant_id: TenantId) -> Tenant:
        """Raises TenantNotFoundError."""
        ...

    async def list_all(self) -> list[Tenant]: ...

    async def names(self, tenant_ids: Collection[TenantId]) -> dict[TenantId, str]: ...

    async def add(self, tenant: Tenant) -> None:
        """Raises SlugTakenError."""
        ...

    async def save(self, tenant: Tenant) -> None: ...


class LocationRepository(Protocol):
    """Tenant-scoped (RLS)."""

    async def get(self, location_id: UUID) -> Location:
        """Raises LocationNotFoundError."""
        ...

    async def list(self) -> list[Location]: ...

    async def add(self, location: Location) -> None: ...

    async def save(self, location: Location) -> None: ...


class WhatsAppNumberRepository(Protocol):
    async def find_by_phone_number_id(self, phone_number_id: str) -> WhatsAppNumber | None: ...

    async def list_for_tenant(self, tenant_id: TenantId) -> list[WhatsAppNumber]: ...

    async def add(self, number: WhatsAppNumber) -> None:
        """Raises PhoneNumberIdTakenError."""
        ...
