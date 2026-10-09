from __future__ import annotations

from typing import Protocol

from app.platform.contacts.domain.repositories import ContactRepository
from app.shared.application.unit_of_work import UnitOfWork


class ContactsUnitOfWork(UnitOfWork, Protocol):
    @property
    def contacts(self) -> ContactRepository: ...
