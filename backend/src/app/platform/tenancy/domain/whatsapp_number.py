"""A WhatsApp Business number connected to a tenant (PRD PL-1.2).

Incoming webhooks carry Meta's `phone_number_id`; looking it up here tells us the tenant
BEFORE any tenant context exists, so this table is platform-level (no RLS).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.platform.tenancy.domain.errors import InvalidPhoneNumberIdError
from app.platform.tenancy.domain.events import WhatsAppNumberConnected
from app.shared.kernel.actor import Actor
from app.shared.kernel.entity import AggregateRoot
from app.shared.kernel.ids import TenantId


@dataclass(kw_only=True, eq=False)
class WhatsAppNumber(AggregateRoot):
    tenant_id: TenantId
    phone_number_id: str  # Meta's id, digits only
    display_phone: str  # e.g. "+91 98765 43210" - shown in the dashboard
    connected_at: datetime
    is_active: bool = True

    @classmethod
    def connect(
        cls,
        *,
        id: UUID,
        tenant_id: TenantId,
        phone_number_id: str,
        display_phone: str,
        actor: Actor,
        at: datetime,
    ) -> WhatsAppNumber:
        phone_number_id = phone_number_id.strip()
        if not phone_number_id.isdigit():
            raise InvalidPhoneNumberIdError("Meta phone_number_id is numeric")
        number = cls(
            id=id,
            tenant_id=tenant_id,
            phone_number_id=phone_number_id,
            display_phone=display_phone.strip(),
            connected_at=at,
        )
        number.record(
            WhatsAppNumberConnected(
                occurred_at=at, whatsapp_number_id=id, tenant_id=tenant_id, actor=actor
            )
        )
        return number
