"""Exchange a refresh token for a new pair (rotation). Also used to SWITCH TENANT.

- unknown / expired token        -> RefreshTokenInvalidError
- already-revoked token (reuse)  -> revoke the whole family, then RefreshTokenInvalidError
- user lost access to the tenant -> the new session has no tenant selected
"""

from __future__ import annotations

from dataclasses import dataclass

from app.platform.identity.application.dto import SessionDTO
from app.platform.identity.application.sessions import SessionIssuer, hash_refresh_token
from app.platform.identity.application.unit_of_work import IdentityUnitOfWork
from app.platform.identity.domain.errors import NotAMemberError, RefreshTokenInvalidError
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import TenantId


@dataclass(frozen=True)
class RefreshSessionCommand:
    refresh_token: str
    switch_to_tenant: TenantId | None = None


class RefreshUserSession:
    def __init__(self, uow: IdentityUnitOfWork, sessions: SessionIssuer, clock: Clock) -> None:
        self._uow, self._sessions, self._clock = uow, sessions, clock

    async def __call__(self, cmd: RefreshSessionCommand) -> SessionDTO:
        now = self._clock.now()
        async with self._uow as uow:
            current = await uow.refresh_sessions.find_by_hash(hash_refresh_token(cmd.refresh_token))
            if current is None or current.is_expired(now):
                raise RefreshTokenInvalidError()
            if current.is_revoked():
                await uow.refresh_sessions.revoke_family(current.family_id, now)
                await uow.commit()
                raise RefreshTokenInvalidError("Session ended for security reasons, log in again")

            user = await uow.users.get(current.user_id)
            if not user.is_active:
                raise RefreshTokenInvalidError()

            tenant_id = cmd.switch_to_tenant or current.active_tenant_id
            if cmd.switch_to_tenant and user.role_in(cmd.switch_to_tenant) is None:
                raise NotAMemberError()
            if tenant_id and user.role_in(tenant_id) is None:
                tenant_id = user.default_tenant()

            dto, new_session = await self._sessions.issue(
                uow, user, tenant_id, family_id=current.family_id
            )
            current.revoke(now, replaced_by=new_session.id)
            await uow.refresh_sessions.save(current)
            await uow.commit()
        return dto
