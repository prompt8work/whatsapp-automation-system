"""Identity events. Ids only - never emails, names or password hashes."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.shared.kernel.actor import Actor
from app.shared.kernel.events import DomainEvent
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role


@dataclass(frozen=True, kw_only=True)
class UserCreated(DomainEvent):
    user_id: UUID
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class MembershipGranted(DomainEvent):
    user_id: UUID
    tenant_id: TenantId
    role: Role
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class MembershipRoleChanged(DomainEvent):
    user_id: UUID
    tenant_id: TenantId
    old_role: Role
    new_role: Role
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class MembershipRevoked(DomainEvent):
    user_id: UUID
    tenant_id: TenantId
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class PasswordChanged(DomainEvent):
    user_id: UUID
