from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.shared.kernel.actor import Actor
from app.shared.kernel.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class TenantCreated(DomainEvent):
    tenant_id: UUID
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class TenantUpdated(DomainEvent):
    tenant_id: UUID
    changed: tuple[str, ...]
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class TenantStatusChanged(DomainEvent):
    tenant_id: UUID
    status: str
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class ModuleEnabled(DomainEvent):
    tenant_id: UUID
    module_key: str
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class ModuleDisabled(DomainEvent):
    tenant_id: UUID
    module_key: str
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class ModuleSettingsUpdated(DomainEvent):
    tenant_id: UUID
    module_key: str
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class LocationAdded(DomainEvent):
    location_id: UUID
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class LocationUpdated(DomainEvent):
    location_id: UUID
    actor: Actor


@dataclass(frozen=True, kw_only=True)
class WhatsAppNumberConnected(DomainEvent):
    whatsapp_number_id: UUID
    tenant_id: UUID
    actor: Actor
