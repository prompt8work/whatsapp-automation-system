from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.platform.identity.domain.user import User
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role


@dataclass(frozen=True)
class MembershipDTO:
    tenant_id: TenantId
    tenant_name: str
    role: Role


@dataclass(frozen=True)
class MeDTO:
    user_id: UUID
    email: str
    full_name: str
    is_super_admin: bool
    active_tenant_id: TenantId | None
    role: Role | None
    permissions: list[str]
    memberships: list[MembershipDTO]


@dataclass(frozen=True)
class SessionDTO:
    access_token: str
    access_expires_at: datetime
    refresh_token: str  # goes ONLY into the httpOnly cookie, never into a JSON body
    refresh_expires_at: datetime
    me: MeDTO


@dataclass(frozen=True)
class MemberDTO:
    user_id: UUID
    email: str
    full_name: str
    role: Role
    is_active: bool

    @classmethod
    def from_domain(cls, user: User, tenant_id: TenantId) -> MemberDTO:
        role = user.role_in(tenant_id)
        assert role is not None
        return cls(user.id, user.email, user.full_name, role, user.is_active)
