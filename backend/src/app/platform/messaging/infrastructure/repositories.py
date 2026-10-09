from __future__ import annotations

from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import RowMapping, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.messaging.domain.message import Direction, Message, MessageStatus
from app.platform.messaging.infrastructure.tables import messages, whatsapp_credentials
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.kernel.errors import NotFoundError
from app.shared.kernel.ids import TenantId


def _message(row: RowMapping) -> Message:
    return Message(
        id=row["id"],
        tenant_id=TenantId(row["tenant_id"]),
        contact_id=row["contact_id"],
        direction=Direction(row["direction"]),
        phone_number_id=row["phone_number_id"],
        wa_message_id=row["wa_message_id"],
        content=dict(row["content"]),
        meta=dict(row["meta"]),
        status=MessageStatus(row["status"]),
        error=row["error"],
        attempts=row["attempts"],
        created_at=row["created_at"],
    )


def _row(m: Message) -> dict[str, Any]:
    return {
        "id": m.id,
        "tenant_id": m.tenant_id,
        "contact_id": m.contact_id,
        "direction": m.direction.value,
        "phone_number_id": m.phone_number_id,
        "wa_message_id": m.wa_message_id,
        "content": m.content,
        "meta": m.meta,
        "status": m.status.value,
        "error": m.error,
        "attempts": m.attempts,
        "created_at": m.created_at,
    }


class SqlMessageRepository:
    def __init__(self, session: AsyncSession, uow: UnitOfWork) -> None:
        self._session, self._uow = session, uow

    async def get(self, message_id: UUID) -> Message:
        row = (
            (await self._session.execute(select(messages).where(messages.c.id == message_id)))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise NotFoundError("Message not found")
        return _message(row)

    async def add_inbound(self, message: Message) -> bool:
        result = await self._session.execute(
            insert(messages)
            .values(_row(message))
            .on_conflict_do_nothing(
                index_elements=["wa_message_id"],
                index_where=messages.c.wa_message_id.isnot(None),
            )
            .returning(messages.c.id)
        )
        return result.scalar_one_or_none() is not None

    async def add(self, message: Message) -> None:
        await self._session.execute(insert(messages).values(_row(message)))

    async def find_by_wa_id(self, wa_message_id: str) -> Message | None:
        row = (
            (
                await self._session.execute(
                    select(messages).where(messages.c.wa_message_id == wa_message_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        return _message(row) if row else None

    async def save(self, message: Message) -> None:
        await self._session.execute(
            update(messages).where(messages.c.id == message.id).values(_row(message))
        )


class SqlCredentialStore:
    """Fernet (AES-128-CBC + HMAC) encryption with CREDENTIALS_KEY; plaintext never stored."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], key: str) -> None:
        self._session_factory = session_factory
        self._fernet = Fernet(key.encode()) if key else None

    async def get(self, phone_number_id: str) -> str | None:
        if self._fernet is None:
            return None
        async with self._session_factory() as session:
            token = (
                await session.execute(
                    select(whatsapp_credentials.c.access_token_encrypted).where(
                        whatsapp_credentials.c.phone_number_id == phone_number_id
                    )
                )
            ).scalar_one_or_none()
        return self._fernet.decrypt(token.encode()).decode() if token else None

    async def put(self, phone_number_id: str, access_token: str) -> None:
        if self._fernet is None:
            raise RuntimeError("Set CREDENTIALS_KEY before storing WhatsApp access tokens")
        encrypted = self._fernet.encrypt(access_token.encode()).decode()
        async with self._session_factory() as session, session.begin():
            await session.execute(
                insert(whatsapp_credentials)
                .values(phone_number_id=phone_number_id, access_token_encrypted=encrypted)
                .on_conflict_do_update(
                    index_elements=["phone_number_id"],
                    set_={"access_token_encrypted": encrypted, "updated_at": func.now()},
                )
            )


class LocalCredentialStore:
    """For WHATSAPP_SENDER=recording: every number has a dummy token, nothing is stored."""

    async def get(self, phone_number_id: str) -> str | None:
        return "local-recording-token"

    async def put(self, phone_number_id: str, access_token: str) -> None:
        return None
