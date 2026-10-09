from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.platform.tenancy.domain.location import Location
from app.platform.tenancy.domain.tenant import Tenant
from app.platform.tenancy.domain.whatsapp_number import WhatsAppNumber
from app.shared.kernel.ids import TenantId


@dataclass(frozen=True)
class TenantDTO:
    id: TenantId
    name: str
    slug: str
    timezone: str
    status: str
    modules: dict[str, dict[str, Any]]
    created_at: datetime

    @classmethod
    def from_domain(cls, t: Tenant) -> TenantDTO:
        return cls(
            TenantId(t.id),
            t.name,
            t.slug,
            t.timezone,
            t.status.value,
            dict(t.modules),
            t.created_at,
        )


@dataclass(frozen=True)
class LocationDTO:
    id: UUID
    name: str
    address: str
    timezone: str
    is_active: bool

    @classmethod
    def from_domain(cls, loc: Location) -> LocationDTO:
        return cls(loc.id, loc.name, loc.address, loc.timezone, loc.is_active)


@dataclass(frozen=True)
class WhatsAppNumberDTO:
    id: UUID
    tenant_id: TenantId
    phone_number_id: str
    display_phone: str
    is_active: bool

    @classmethod
    def from_domain(cls, n: WhatsAppNumber) -> WhatsAppNumberDTO:
        return cls(n.id, n.tenant_id, n.phone_number_id, n.display_phone, n.is_active)


@dataclass(frozen=True)
class TenantRoute:
    """Where an incoming webhook belongs (used by the conversation pipeline in step 3)."""

    tenant_id: TenantId
    whatsapp_number_id: UUID
    timezone: str
    enabled_modules: frozenset[str]
