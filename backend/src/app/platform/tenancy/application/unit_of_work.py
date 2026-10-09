from __future__ import annotations

from typing import Protocol

from app.platform.tenancy.domain.repositories import (
    LocationRepository,
    TenantRepository,
    WhatsAppNumberRepository,
)
from app.shared.application.unit_of_work import UnitOfWork


class TenancyUnitOfWork(UnitOfWork, Protocol):
    @property
    def tenants(self) -> TenantRepository: ...

    @property
    def locations(self) -> LocationRepository:
        """Only usable when the Unit of Work is scoped to a tenant (RLS)."""
        ...

    @property
    def whatsapp_numbers(self) -> WhatsAppNumberRepository: ...
