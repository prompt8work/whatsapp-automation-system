"""User aggregate: a dashboard login, possibly a member of several tenants (PRD PL-8.1).

Users are platform-level (one email = one user across tenants), so this is a plain
AggregateRoot; tenant access is expressed by `memberships`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.platform.identity.domain.errors import (
    AlreadyMemberError,
    CannotChangeOwnMembershipError,
    InvalidEmailError,
    NotAMemberError,
    WeakPasswordError,
)
from app.platform.identity.domain.events import (
    MembershipGranted,
    MembershipRevoked,
    MembershipRoleChanged,
    PasswordChanged,
    UserCreated,
)
from app.shared.kernel.actor import Actor
from app.shared.kernel.entity import AggregateRoot
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 10


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > 254 or not _EMAIL.match(email):
        raise InvalidEmailError("Enter a valid email address")
    return email


def check_password_strength(password: str) -> None:
    """Checked on the plain password BEFORE hashing (the domain only ever stores hashes)."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


@dataclass(frozen=True)
class Membership:
    tenant_id: TenantId
    role: Role


@dataclass(kw_only=True, eq=False)
class User(AggregateRoot):
    email: str
    full_name: str
    password_hash: str
    created_at: datetime
    is_super_admin: bool = False
    is_active: bool = True
    memberships: list[Membership] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        email: str,
        full_name: str,
        password_hash: str,
        actor: Actor,
        at: datetime,
        is_super_admin: bool = False,
    ) -> User:
        user = cls(
            id=id,
            email=normalize_email(email),
            full_name=" ".join(full_name.split()) or email,
            password_hash=password_hash,
            created_at=at,
            is_super_admin=is_super_admin,
        )
        user.record(UserCreated(occurred_at=at, user_id=id, actor=actor))
        return user

    # ---------------------------------------------------------------- queries
    def role_in(self, tenant_id: TenantId) -> Role | None:
        return next((m.role for m in self.memberships if m.tenant_id == tenant_id), None)

    def default_tenant(self) -> TenantId | None:
        return self.memberships[0].tenant_id if self.memberships else None

    # ---------------------------------------------------------------- commands
    def grant_membership(
        self, tenant_id: TenantId, role: Role, *, actor: Actor, at: datetime
    ) -> None:
        if self.role_in(tenant_id) is not None:
            raise AlreadyMemberError()
        self.memberships.append(Membership(tenant_id, role))
        self.record(
            MembershipGranted(
                occurred_at=at, user_id=self.id, tenant_id=tenant_id, role=role, actor=actor
            )
        )

    def change_role(self, tenant_id: TenantId, role: Role, *, actor: Actor, at: datetime) -> None:
        self._ensure_not_self(actor)
        old = self.role_in(tenant_id)
        if old is None:
            raise NotAMemberError()
        if old is role:
            return
        self.memberships = [
            Membership(tenant_id, role) if m.tenant_id == tenant_id else m for m in self.memberships
        ]
        self.record(
            MembershipRoleChanged(
                occurred_at=at,
                user_id=self.id,
                tenant_id=tenant_id,
                old_role=old,
                new_role=role,
                actor=actor,
            )
        )

    def revoke_membership(self, tenant_id: TenantId, *, actor: Actor, at: datetime) -> None:
        self._ensure_not_self(actor)
        if self.role_in(tenant_id) is None:
            raise NotAMemberError()
        self.memberships = [m for m in self.memberships if m.tenant_id != tenant_id]
        self.record(
            MembershipRevoked(occurred_at=at, user_id=self.id, tenant_id=tenant_id, actor=actor)
        )

    def upgrade_password_hash(self, password_hash: str) -> None:
        """Same password, stronger hashing parameters (done silently at login). No event."""
        self.password_hash = password_hash

    def change_password_hash(self, password_hash: str, *, at: datetime) -> None:
        self.password_hash = password_hash
        self.record(PasswordChanged(occurred_at=at, user_id=self.id))

    def _ensure_not_self(self, actor: Actor) -> None:
        if actor.id == self.id:
            raise CannotChangeOwnMembershipError("Ask another admin to change your own access")
