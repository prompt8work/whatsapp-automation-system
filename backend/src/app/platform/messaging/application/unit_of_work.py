from __future__ import annotations

from typing import Protocol

from app.platform.messaging.domain.repositories import MessageRepository
from app.shared.application.unit_of_work import UnitOfWork


class MessagingUnitOfWork(UnitOfWork, Protocol):
    @property
    def messages(self) -> MessageRepository: ...
