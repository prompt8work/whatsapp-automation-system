from __future__ import annotations

from app.platform.contacts.infrastructure.repositories import SqlContactRepository
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork


class SqlContactsUnitOfWork(SqlUnitOfWork):
    contacts: SqlContactRepository

    def _create_repositories(self) -> None:
        self.contacts = SqlContactRepository(self.session, self)
