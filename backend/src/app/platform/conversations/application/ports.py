"""What the conversation pipeline needs from other modules - as small ports, so the pipeline
can be tested with fakes. Bootstrap adapts the real contacts / messaging / tenancy modules."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.platform.messaging.contracts import InboundMessage, StatusUpdate
from app.platform.tenancy.contracts import TenantRoute
from app.shared.application.conversation import ContactInfo
from app.shared.kernel.ids import TenantId


class TenantResolver(Protocol):
    async def resolve(self, phone_number_id: str) -> TenantRoute | None: ...


class ContactGateway(Protocol):
    async def resolve(
        self, tenant_id: TenantId, wa_id: str, profile_name: str | None
    ) -> ContactInfo: ...

    async def set_opt_out(self, tenant_id: TenantId, contact_id: UUID, opted_out: bool) -> None: ...

    async def grant_consent(self, tenant_id: TenantId, contact_id: UUID) -> None: ...


class InboundLog(Protocol):
    async def record(
        self, tenant_id: TenantId, contact_id: UUID, message: InboundMessage
    ) -> UUID | None:
        """New message id, or None for a duplicate delivery."""
        ...

    async def mark_processed(self, tenant_id: TenantId, message_id: UUID) -> None: ...

    async def load(self, tenant_id: TenantId, message_id: UUID) -> tuple[InboundMessage, bool]:
        """(message, already_processed) - for the safety-net job."""
        ...

    async def record_status(self, tenant_id: TenantId, update: StatusUpdate) -> None: ...


class HandoverDesk(Protocol):
    """Staff takeover (PRD PL-5). The inbox module implements it in build step 6."""

    async def is_active(self, tenant_id: TenantId, contact_id: UUID) -> bool: ...

    async def request(self, tenant_id: TenantId, contact_id: UUID, reason: str) -> None: ...
