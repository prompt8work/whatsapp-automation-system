from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.platform.identity.domain.refresh_session import RefreshSession
from app.platform.identity.domain.user import User
from app.shared.kernel.ids import TenantId


class UserRepository(Protocol):
    async def get(self, user_id: UUID) -> User:
        """Raises UserNotFoundError."""
        ...

    async def find_by_email(self, email: str) -> User | None: ...

    async def list_members(self, tenant_id: TenantId) -> list[User]: ...

    async def add(self, user: User) -> None:
        """Raises EmailAlreadyUsedError."""
        ...

    async def save(self, user: User) -> None: ...


class RefreshSessionRepository(Protocol):
    async def find_by_hash(self, token_hash: str) -> RefreshSession | None: ...

    async def add(self, session: RefreshSession) -> None: ...

    async def save(self, session: RefreshSession) -> None: ...

    async def revoke_family(self, family_id: UUID, at: datetime) -> None: ...
