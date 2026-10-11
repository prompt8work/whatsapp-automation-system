from __future__ import annotations

from app.platform.messaging.infrastructure.repositories import (
    SqlMessageRepository,
    SqlTemplateMappings,
)
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork


class SqlMessagingUnitOfWork(SqlUnitOfWork):
    messages: SqlMessageRepository
    templates: SqlTemplateMappings

    def _create_repositories(self) -> None:
        self.messages = SqlMessageRepository(self.session, self)
        self.templates = SqlTemplateMappings(self.session, self._tenant_id)
