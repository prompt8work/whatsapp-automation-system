"""SQL Unit of Work for this module: the shared one + this module's repositories."""

from __future__ import annotations

from app.modules._template.infrastructure.repositories import SqlItemRepository
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork


class SqlTemplateUnitOfWork(SqlUnitOfWork):
    items: SqlItemRepository

    def _create_repositories(self) -> None:
        self.items = SqlItemRepository(self.session, self)
