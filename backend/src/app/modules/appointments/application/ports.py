"""What appointments needs from the platform, as small ports (adapted in wiring.py)."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId


class ClinicDirectory(Protocol):
    """Tenancy facts: a location's timezone and this module's settings for the tenant."""

    async def timezone(self, tenant_id: TenantId, location_id: UUID) -> str: ...

    async def settings(self, tenant_id: TenantId) -> dict[str, Any]: ...

    async def location_names(self, tenant_id: TenantId) -> dict[UUID, str]: ...


class PatientContacts(Protocol):
    """Contacts facts. Reading a phone number is audited (it is personal data)."""

    async def phone(self, tenant_id: TenantId, contact_id: UUID, actor: Actor) -> str: ...

    async def contact_for_phone(self, tenant_id: TenantId, phone: str) -> UUID:
        """Find or create the contact for a phone number (staff booking on someone's behalf)."""
        ...
