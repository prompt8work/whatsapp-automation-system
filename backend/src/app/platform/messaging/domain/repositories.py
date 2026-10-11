from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.platform.messaging.domain.message import Message
from app.platform.messaging.domain.templates import TemplateMapping


class MessageRepository(Protocol):
    """Tenant-scoped (RLS)."""

    async def get(self, message_id: UUID) -> Message: ...

    async def add_inbound(self, message: Message) -> bool:
        """False if this wa_message_id was already stored (webhook retry) - PRD AC-11."""
        ...

    async def add(self, message: Message) -> None: ...

    async def find_by_wa_id(self, wa_message_id: str) -> Message | None: ...

    async def save(self, message: Message) -> None: ...


class CredentialStore(Protocol):
    """Access tokens per connected number, encrypted at rest. Platform-level."""

    async def get(self, phone_number_id: str) -> str | None: ...

    async def put(self, phone_number_id: str, access_token: str) -> None: ...


class TemplateMappings(Protocol):
    """Tenant-scoped (RLS)."""

    async def get(self, slot: str) -> TemplateMapping | None: ...

    async def list(self) -> list[TemplateMapping]: ...

    async def put(self, mapping: TemplateMapping) -> None: ...

    async def delete(self, slot: str) -> None: ...
