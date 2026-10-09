"""Placeholder HandoverDesk until the staff inbox exists (build step 6): never active, and a
handover request is only logged."""

from __future__ import annotations

import logging
from uuid import UUID

from app.shared.kernel.ids import TenantId

log = logging.getLogger(__name__)


class LoggingHandoverDesk:
    async def is_active(self, tenant_id: TenantId, contact_id: UUID) -> bool:
        return False

    async def request(self, tenant_id: TenantId, contact_id: UUID, reason: str) -> None:
        log.info("handover.requested", extra={"contact_id": str(contact_id), "reason": reason})
