"""Refresh sessions: one row per issued refresh token, grouped into a `family` per login.

Rotation: every refresh revokes the presented token and issues a new one in the same family.
Reuse detection: if an already-revoked token is presented, someone copied it - the whole
family is revoked and the user must log in again.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.shared.kernel.entity import AggregateRoot
from app.shared.kernel.ids import TenantId


@dataclass(kw_only=True, eq=False)
class RefreshSession(AggregateRoot):
    user_id: UUID
    family_id: UUID
    token_hash: str  # sha256 of the token; the token itself is never stored
    active_tenant_id: TenantId | None
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    replaced_by: UUID | None = None

    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def revoke(self, now: datetime, *, replaced_by: UUID | None = None) -> None:
        if self.revoked_at is None:
            self.revoked_at = now
            self.replaced_by = replaced_by
