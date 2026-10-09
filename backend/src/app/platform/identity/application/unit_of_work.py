from __future__ import annotations

from typing import Protocol

from app.platform.identity.domain.repositories import RefreshSessionRepository, UserRepository
from app.shared.application.unit_of_work import UnitOfWork


class IdentityUnitOfWork(UnitOfWork, Protocol):
    @property
    def users(self) -> UserRepository: ...

    @property
    def refresh_sessions(self) -> RefreshSessionRepository: ...
