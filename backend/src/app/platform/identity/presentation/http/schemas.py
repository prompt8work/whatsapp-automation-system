from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.platform.identity.application.dto import MeDTO, MemberDTO, SessionDTO
from app.shared.kernel.roles import Role


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    tenant_id: UUID | None = None


class RefreshRequest(BaseModel):
    tenant_id: UUID | None = Field(default=None, description="Switch to this tenant")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class MembershipResponse(BaseModel):
    tenant_id: UUID
    tenant_name: str
    role: Role


class MeResponse(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    is_super_admin: bool
    active_tenant_id: UUID | None
    role: Role | None
    permissions: list[str]
    memberships: list[MembershipResponse]

    @classmethod
    def from_dto(cls, me: MeDTO) -> MeResponse:
        return cls(
            user_id=me.user_id,
            email=me.email,
            full_name=me.full_name,
            is_super_admin=me.is_super_admin,
            active_tenant_id=me.active_tenant_id,
            role=me.role,
            permissions=me.permissions,
            memberships=[
                MembershipResponse(tenant_id=m.tenant_id, tenant_name=m.tenant_name, role=m.role)
                for m in me.memberships
            ],
        )


class SessionResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    me: MeResponse

    @classmethod
    def from_dto(cls, session: SessionDTO) -> SessionResponse:
        return cls(
            access_token=session.access_token,
            expires_at=session.access_expires_at,
            me=MeResponse.from_dto(session.me),
        )


class AddMemberRequest(BaseModel):
    email: str = Field(max_length=254)
    full_name: str = Field(min_length=1, max_length=200)
    role: Role
    initial_password: str | None = Field(default=None, min_length=10, max_length=200)


class ChangeMemberRoleRequest(BaseModel):
    role: Role


class MemberResponse(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    role: Role
    is_active: bool

    @classmethod
    def from_dto(cls, m: MemberDTO) -> MemberResponse:
        return cls(
            user_id=m.user_id,
            email=m.email,
            full_name=m.full_name,
            role=m.role,
            is_active=m.is_active,
        )
