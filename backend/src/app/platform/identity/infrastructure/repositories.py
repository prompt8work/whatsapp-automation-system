from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.domain.errors import EmailAlreadyUsedError, UserNotFoundError
from app.platform.identity.domain.refresh_session import RefreshSession
from app.platform.identity.domain.user import Membership, User
from app.platform.identity.infrastructure.tables import memberships, refresh_sessions, users
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.kernel.errors import ConcurrencyConflictError
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role


class SqlUserRepository:
    def __init__(self, session: AsyncSession, uow: UnitOfWork) -> None:
        self._session, self._uow = session, uow

    async def get(self, user_id: UUID) -> User:
        found = await self._load(users.c.id == user_id)
        if not found:
            raise UserNotFoundError()
        return found[0]

    async def find_by_email(self, email: str) -> User | None:
        found = await self._load(users.c.email == email)
        return found[0] if found else None

    async def list_members(self, tenant_id: TenantId) -> list[User]:
        member_ids = select(memberships.c.user_id).where(memberships.c.tenant_id == tenant_id)
        return await self._load(users.c.id.in_(member_ids))

    async def add(self, user: User) -> None:
        try:
            async with self._session.begin_nested():
                await self._session.execute(insert(users).values(_user_row(user)))
        except IntegrityError as exc:
            raise EmailAlreadyUsedError() from exc
        await self._write_memberships(user)
        self._uow.track(user)

    async def save(self, user: User) -> None:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(users)
                .where(users.c.id == user.id, users.c.version == user.version)
                .values(_user_row(user) | {"version": user.version + 1})
            ),
        )
        if result.rowcount != 1:
            raise ConcurrencyConflictError()
        user.version += 1
        await self._session.execute(delete(memberships).where(memberships.c.user_id == user.id))
        await self._write_memberships(user)
        self._uow.track(user)

    async def _write_memberships(self, user: User) -> None:
        if user.memberships:
            await self._session.execute(
                insert(memberships),
                [
                    {"user_id": user.id, "tenant_id": m.tenant_id, "role": m.role.value}
                    for m in user.memberships
                ],
            )

    async def _load(self, where: Any) -> list[User]:
        rows = (await self._session.execute(select(users).where(where))).mappings().all()
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        member_rows = (
            await self._session.execute(
                select(memberships)
                .where(memberships.c.user_id.in_(ids))
                .order_by(memberships.c.tenant_id)
            )
        ).mappings()
        by_user: dict[UUID, list[Membership]] = {i: [] for i in ids}
        for m in member_rows:
            by_user[m["user_id"]].append(Membership(TenantId(m["tenant_id"]), Role(m["role"])))
        result = [
            User(
                id=r["id"],
                email=r["email"],
                full_name=r["full_name"],
                password_hash=r["password_hash"],
                is_super_admin=r["is_super_admin"],
                is_active=r["is_active"],
                created_at=r["created_at"],
                version=r["version"],
                memberships=by_user[r["id"]],
            )
            for r in rows
        ]
        for user in result:
            self._uow.track(user)
        return result


def _user_row(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "password_hash": user.password_hash,
        "is_super_admin": user.is_super_admin,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "version": user.version,
    }


class SqlRefreshSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_hash(self, token_hash: str) -> RefreshSession | None:
        row = (
            (
                await self._session.execute(
                    select(refresh_sessions)
                    .where(refresh_sessions.c.token_hash == token_hash)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return RefreshSession(
            id=row["id"],
            user_id=row["user_id"],
            family_id=row["family_id"],
            token_hash=row["token_hash"],
            active_tenant_id=TenantId(row["active_tenant_id"]) if row["active_tenant_id"] else None,
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
            replaced_by=row["replaced_by"],
        )

    async def add(self, session: RefreshSession) -> None:
        await self._session.execute(insert(refresh_sessions).values(_session_row(session)))

    async def save(self, session: RefreshSession) -> None:
        await self._session.execute(
            update(refresh_sessions)
            .where(refresh_sessions.c.id == session.id)
            .values(revoked_at=session.revoked_at, replaced_by=session.replaced_by)
        )

    async def revoke_family(self, family_id: UUID, at: datetime) -> None:
        await self._session.execute(
            update(refresh_sessions)
            .where(
                refresh_sessions.c.family_id == family_id, refresh_sessions.c.revoked_at.is_(None)
            )
            .values(revoked_at=at)
        )


def _session_row(session: RefreshSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "user_id": session.user_id,
        "family_id": session.family_id,
        "token_hash": session.token_hash,
        "active_tenant_id": session.active_tenant_id,
        "issued_at": session.issued_at,
        "expires_at": session.expires_at,
        "revoked_at": session.revoked_at,
        "replaced_by": session.replaced_by,
    }
