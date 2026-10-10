"""What appointments needs from the platform, as small ports (adapted in wiring.py)."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.shared.application.retention import PurgeResult, PurgeTarget
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId


class ClinicDirectory(Protocol):
    """Tenancy facts: a location's timezone and this module's settings for the tenant."""

    async def timezone(self, tenant_id: TenantId, location_id: UUID) -> str: ...

    async def tenant_timezone(self, tenant_id: TenantId) -> str: ...

    async def settings(self, tenant_id: TenantId) -> dict[str, Any]: ...

    async def location_names(self, tenant_id: TenantId) -> dict[UUID, str]: ...


class PatientContacts(Protocol):
    """Contacts facts. Reading a phone number is audited (it is personal data)."""

    async def phone(self, tenant_id: TenantId, contact_id: UUID, actor: Actor) -> str: ...

    async def contact_for_phone(self, tenant_id: TenantId, phone: str) -> UUID:
        """Find or create the contact for a phone number (staff booking on someone's behalf)."""
        ...


class PatientEraser(Protocol):
    """Deletes a patient and all their cases now (the retention purge, AP-10.11)."""

    async def purge_patient(self, tenant_id: TenantId, patient_id: UUID) -> PurgeResult: ...


class DeletionRecorder(Protocol):
    """Writes the deletion record - counts, no personal data (AP-10.5, AP-10.13)."""

    async def __call__(
        self, tenant_id: TenantId, purger: str, target: PurgeTarget, result: PurgeResult
    ) -> None: ...
