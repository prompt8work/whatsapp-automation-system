from __future__ import annotations

from typing import Protocol

from app.platform.conversations.domain.repositories import SessionRepository
from app.shared.application.unit_of_work import UnitOfWork


class ConversationsUnitOfWork(UnitOfWork, Protocol):
    @property
    def sessions(self) -> SessionRepository: ...
