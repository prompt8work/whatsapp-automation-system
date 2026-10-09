from __future__ import annotations

from app.platform.tenancy.infrastructure.repositories import (
    SqlLocationRepository,
    SqlTenantRepository,
    SqlWhatsAppNumberRepository,
)
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork


class SqlTenancyUnitOfWork(SqlUnitOfWork):
    tenants: SqlTenantRepository
    locations: SqlLocationRepository
    whatsapp_numbers: SqlWhatsAppNumberRepository

    def _create_repositories(self) -> None:
        self.tenants = SqlTenantRepository(self.session, self)
        self.locations = SqlLocationRepository(self.session, self)
        self.whatsapp_numbers = SqlWhatsAppNumberRepository(self.session, self)
