"""Who is calling - framework-free, so use cases can receive it (ARCHITECTURE §8.8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from app.shared.kernel.actor import Actor
from app.shared.kernel.errors import DomainError
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role


class InvalidAccessTokenError(DomainError):
    code = "auth.invalid_token"


class PermissionDeniedError(DomainError):
    code = "auth.permission_denied"


class NoTenantSelectedError(DomainError):
    code = "auth.no_tenant"


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    tenant_id: TenantId | None  # None: super-admin acting at platform level
    role: Role | None
    is_super_admin: bool = False
    permissions: frozenset[str] = field(default_factory=frozenset)

    @property
    def actor(self) -> Actor:
        return Actor.staff(self.user_id)

    def can(self, permission: str) -> bool:
        return permission in self.permissions


class AccessTokenVerifier(Protocol):
    def verify(self, token: str) -> Principal:
        """Raises InvalidAccessTokenError."""
        ...
