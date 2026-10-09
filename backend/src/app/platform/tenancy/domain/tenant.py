"""Tenant aggregate: one business (clinic) on the platform (PRD §6.1).

Platform-level record (it IS the tenant), so a plain AggregateRoot. `modules` maps every
ENABLED module key to that tenant's settings for it (PL-1.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.platform.tenancy.domain.errors import ModuleNotEnabledError
from app.platform.tenancy.domain.events import (
    ModuleDisabled,
    ModuleEnabled,
    ModuleSettingsUpdated,
    TenantCreated,
    TenantStatusChanged,
    TenantUpdated,
)
from app.platform.tenancy.domain.values import valid_name, valid_slug, valid_timezone
from app.shared.kernel.actor import Actor
from app.shared.kernel.entity import AggregateRoot


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


@dataclass(kw_only=True, eq=False)
class Tenant(AggregateRoot):
    name: str
    slug: str
    timezone: str
    created_at: datetime
    status: TenantStatus = TenantStatus.ACTIVE
    modules: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def create(
        cls, *, id: UUID, name: str, slug: str, timezone: str, actor: Actor, at: datetime
    ) -> Tenant:
        tenant = cls(
            id=id,
            name=valid_name(name),
            slug=valid_slug(slug),
            timezone=valid_timezone(timezone),
            created_at=at,
        )
        tenant.record(TenantCreated(occurred_at=at, tenant_id=id, actor=actor))
        return tenant

    @property
    def is_active(self) -> bool:
        return self.status is TenantStatus.ACTIVE

    def update(self, *, name: str | None, timezone: str | None, actor: Actor, at: datetime) -> None:
        changed: list[str] = []
        if name is not None and valid_name(name) != self.name:
            self.name = valid_name(name)
            changed.append("name")
        if timezone is not None and valid_timezone(timezone) != self.timezone:
            self.timezone = timezone
            changed.append("timezone")
        if changed:
            self.record(
                TenantUpdated(
                    occurred_at=at, tenant_id=self.id, changed=tuple(changed), actor=actor
                )
            )

    def set_status(self, status: TenantStatus, *, actor: Actor, at: datetime) -> None:
        if status is not self.status:
            self.status = status
            self.record(
                TenantStatusChanged(occurred_at=at, tenant_id=self.id, status=status, actor=actor)
            )

    def enable_module(
        self, key: str, *, settings: dict[str, Any] | None = None, actor: Actor, at: datetime
    ) -> None:
        if key in self.modules:
            return
        self.modules[key] = dict(settings or {})
        self.record(ModuleEnabled(occurred_at=at, tenant_id=self.id, module_key=key, actor=actor))

    def disable_module(self, key: str, *, actor: Actor, at: datetime) -> None:
        if self.modules.pop(key, None) is not None:
            self.record(
                ModuleDisabled(occurred_at=at, tenant_id=self.id, module_key=key, actor=actor)
            )

    def update_module_settings(
        self, key: str, settings: dict[str, Any], *, actor: Actor, at: datetime
    ) -> None:
        if key not in self.modules:
            raise ModuleNotEnabledError(f"Module {key!r} is not enabled for this tenant")
        self.modules[key] = dict(settings)
        self.record(
            ModuleSettingsUpdated(occurred_at=at, tenant_id=self.id, module_key=key, actor=actor)
        )
