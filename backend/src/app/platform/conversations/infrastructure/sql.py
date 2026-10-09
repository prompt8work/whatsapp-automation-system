from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.conversations.domain.session import ConversationSession
from app.platform.conversations.infrastructure.tables import conversation_sessions
from app.shared.infrastructure.serialization import to_jsonable
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork
from app.shared.kernel.ids import TenantId


class SqlSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_and_get(self, contact_id: UUID) -> ConversationSession | None:
        # Transaction-scoped advisory lock: works even before the session row exists,
        # and is released automatically at commit/rollback.
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"conversation:{contact_id}"},
        )
        row = (
            (
                await self._session.execute(
                    select(conversation_sessions).where(
                        conversation_sessions.c.contact_id == contact_id
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return ConversationSession(
            id=row["id"],
            tenant_id=TenantId(row["tenant_id"]),
            contact_id=row["contact_id"],
            flow_key=row["flow_key"],
            step_key=row["step_key"],
            last_flow_key=row["last_flow_key"],
            data=dict(row["data"]),
            attempts=row["attempts"],
            expires_at=row["expires_at"],
            updated_at=row["updated_at"],
        )

    async def save(self, session: ConversationSession) -> None:
        values: dict[str, Any] = {
            "id": session.id,
            "tenant_id": session.tenant_id,
            "contact_id": session.contact_id,
            "flow_key": session.flow_key,
            "step_key": session.step_key,
            "last_flow_key": session.last_flow_key,
            "data": to_jsonable(session.data),
            "attempts": session.attempts,
            "expires_at": session.expires_at,
            "updated_at": session.updated_at,
        }
        update = {k: v for k, v in values.items() if k not in ("id", "tenant_id", "contact_id")}
        await self._session.execute(
            insert(conversation_sessions)
            .values(values)
            .on_conflict_do_update(constraint="uq_conversation_sessions_contact", set_=update)
        )


class SqlConversationsUnitOfWork(SqlUnitOfWork):
    sessions: SqlSessionRepository

    def _create_repositories(self) -> None:
        self.sessions = SqlSessionRepository(self.session)
