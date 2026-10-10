from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.platform.contacts.domain.contact import Contact
from app.platform.contacts.domain.phone import PhoneNumber


class ContactRepository(Protocol):
    """Tenant-scoped (RLS)."""

    async def get(self, contact_id: UUID) -> Contact:
        """Raises ContactNotFoundError."""
        ...

    async def find_by_phone(self, phone: PhoneNumber) -> Contact | None: ...

    async def get_many(self, contact_ids: list[UUID]) -> list[Contact]: ...

    async def search(self, text: str | None, *, limit: int, offset: int) -> list[Contact]: ...

    async def add(self, contact: Contact) -> bool:
        """False if the phone already exists (a concurrent message created it first)."""
        ...

    async def save(self, contact: Contact) -> None: ...
