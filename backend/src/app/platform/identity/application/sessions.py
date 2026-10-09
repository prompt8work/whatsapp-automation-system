"""Shared by Login and Refresh: build the Principal, issue tokens, describe the user.

Refresh tokens are 256-bit random strings. Only their sha256 is stored, so a database leak
does not leak usable tokens.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from app.platform.identity.application.dto import MeDTO, MembershipDTO, SessionDTO
from app.platform.identity.application.ports import AccessTokenIssuer, TenantDirectory
from app.platform.identity.application.unit_of_work import IdentityUnitOfWork
from app.platform.identity.domain.refresh_session import RefreshSession
from app.platform.identity.domain.user import User
from app.shared.application.auth import Principal
from app.shared.application.permissions import PermissionRegistry
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def principal_for(
    user: User, tenant_id: TenantId | None, permissions: PermissionRegistry
) -> Principal:
    role = user.role_in(tenant_id) if tenant_id else None
    return Principal(
        user_id=user.id,
        tenant_id=tenant_id,
        role=role,
        is_super_admin=user.is_super_admin,
        permissions=permissions.for_role(role),
    )


async def describe(user: User, principal: Principal, directory: TenantDirectory) -> MeDTO:
    names = await directory.names([m.tenant_id for m in user.memberships])
    return MeDTO(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_super_admin=user.is_super_admin,
        active_tenant_id=principal.tenant_id,
        role=principal.role,
        permissions=sorted(principal.permissions),
        memberships=[
            MembershipDTO(m.tenant_id, names.get(m.tenant_id, "Unknown"), m.role)
            for m in user.memberships
        ],
    )


@dataclass
class SessionIssuer:
    tokens: AccessTokenIssuer
    permissions: PermissionRegistry
    directory: TenantDirectory
    clock: Clock
    ids: IdGenerator
    refresh_ttl: timedelta

    async def issue(
        self,
        uow: IdentityUnitOfWork,
        user: User,
        tenant_id: TenantId | None,
        *,
        family_id: UUID | None = None,
    ) -> tuple[SessionDTO, RefreshSession]:
        """Adds the new RefreshSession to `uow`; the caller commits."""
        now = self.clock.now()
        principal = principal_for(user, tenant_id, self.permissions)
        access = self.tokens.issue(principal)
        raw_refresh = secrets.token_urlsafe(32)
        session = RefreshSession(
            id=self.ids.new_id(),
            user_id=user.id,
            family_id=family_id or self.ids.new_id(),
            token_hash=hash_refresh_token(raw_refresh),
            active_tenant_id=tenant_id,
            issued_at=now,
            expires_at=now + self.refresh_ttl,
        )
        await uow.refresh_sessions.add(session)
        dto = SessionDTO(
            access_token=access.token,
            access_expires_at=access.expires_at,
            refresh_token=raw_refresh,
            refresh_expires_at=session.expires_at,
            me=await describe(user, principal, self.directory),
        )
        return dto, session
