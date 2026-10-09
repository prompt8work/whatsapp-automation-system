from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.identity.infrastructure.repositories import (
    SqlRefreshSessionRepository,
    SqlUserRepository,
)
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork


class SqlIdentityUnitOfWork(SqlUnitOfWork):
    """Platform-level (no tenant set): identity tables have no RLS."""

    users: SqlUserRepository
    refresh_sessions: SqlRefreshSessionRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory, tenant_id=None)

    def _create_repositories(self) -> None:
        self.users = SqlUserRepository(self.session, self)
        self.refresh_sessions = SqlRefreshSessionRepository(self.session)
