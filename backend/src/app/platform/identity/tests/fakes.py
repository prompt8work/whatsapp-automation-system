from __future__ import annotations

import copy
from collections.abc import Collection
from datetime import datetime, timedelta
from uuid import UUID

from app.platform.identity.application.ports import IssuedAccessToken
from app.platform.identity.domain.errors import EmailAlreadyUsedError, UserNotFoundError
from app.platform.identity.domain.refresh_session import RefreshSession
from app.platform.identity.domain.user import User
from app.shared.application.auth import Principal
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.kernel.ids import TenantId
from app.shared.testing.fakes import FixedClock, InMemoryUnitOfWork


class FakeHasher:
    def __init__(self) -> None:
        self.dummy_calls = 0
        self.outdated: set[str] = set()

    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{password}"

    def needs_rehash(self, password_hash: str) -> bool:
        return password_hash in self.outdated

    def dummy_verify(self, password: str) -> None:
        self.dummy_calls += 1


class FakeTokens:
    def __init__(self, clock: FixedClock) -> None:
        self._clock = clock
        self.issued: list[Principal] = []

    def issue(self, principal: Principal) -> IssuedAccessToken:
        self.issued.append(principal)
        return IssuedAccessToken(
            f"access-{len(self.issued)}", self._clock.now() + timedelta(minutes=15)
        )


class FakeDirectory:
    def __init__(self, names: dict[TenantId, str] | None = None) -> None:
        self._names = names or {}

    async def names(self, tenant_ids: Collection[TenantId]) -> dict[TenantId, str]:
        return {t: self._names[t] for t in tenant_ids if t in self._names}


class InMemoryUserRepository:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self.rows: dict[UUID, User] = {}

    def _copy(self, user: User) -> User:
        stored = copy.deepcopy(user)
        stored.pull_events()
        return stored

    async def get(self, user_id: UUID) -> User:
        if user_id not in self.rows:
            raise UserNotFoundError()
        user = self._copy(self.rows[user_id])
        self._uow.track(user)
        return user

    async def find_by_email(self, email: str) -> User | None:
        for user in self.rows.values():
            if user.email == email:
                return await self.get(user.id)
        return None

    async def list_members(self, tenant_id: TenantId) -> list[User]:
        return [self._copy(u) for u in self.rows.values() if u.role_in(tenant_id)]

    async def add(self, user: User) -> None:
        if any(u.email == user.email for u in self.rows.values()):
            raise EmailAlreadyUsedError()
        self.rows[user.id] = self._copy(user)
        self._uow.track(user)

    async def save(self, user: User) -> None:
        user.version += 1
        self.rows[user.id] = self._copy(user)
        self._uow.track(user)


class InMemoryRefreshSessionRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, RefreshSession] = {}

    async def find_by_hash(self, token_hash: str) -> RefreshSession | None:
        for s in self.rows.values():
            if s.token_hash == token_hash:
                return copy.deepcopy(s)
        return None

    async def add(self, session: RefreshSession) -> None:
        self.rows[session.id] = copy.deepcopy(session)

    async def save(self, session: RefreshSession) -> None:
        self.rows[session.id] = copy.deepcopy(session)

    async def revoke_family(self, family_id: UUID, at: datetime) -> None:
        for s in self.rows.values():
            if s.family_id == family_id:
                s.revoke(at)


class InMemoryIdentityUnitOfWork(InMemoryUnitOfWork):
    def __init__(self) -> None:
        super().__init__()
        self.users = InMemoryUserRepository(self)
        self.refresh_sessions = InMemoryRefreshSessionRepository()
