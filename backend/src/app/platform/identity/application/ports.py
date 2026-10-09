"""Ports the identity use cases need. Implemented in identity/infrastructure (or by bootstrap)."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.shared.application.auth import Principal
from app.shared.kernel.ids import TenantId


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...

    def needs_rehash(self, password_hash: str) -> bool: ...

    def dummy_verify(self, password: str) -> None:
        """Spend the same time as `verify` when the user does not exist (no timing oracle)."""
        ...


@dataclass(frozen=True)
class IssuedAccessToken:
    token: str
    expires_at: datetime


class AccessTokenIssuer(Protocol):
    def issue(self, principal: Principal) -> IssuedAccessToken: ...


class TenantDirectory(Protocol):
    """Tenant names for the "switch clinic" menu. Implemented by bootstrap on top of tenancy."""

    async def names(self, tenant_ids: Collection[TenantId]) -> dict[TenantId, str]: ...
