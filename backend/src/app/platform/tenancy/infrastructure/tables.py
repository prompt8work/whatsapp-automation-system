"""Tenancy tables.

- tenants, whatsapp_numbers: platform-level (no RLS) - needed before a tenant is known.
- locations: tenant-owned -> RLS (enable_tenant_rls in the migration).
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.shared.infrastructure.tables import metadata

tenants = Table(
    "tenants",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("slug", String(40), nullable=False, unique=True),
    Column("timezone", String(64), nullable=False),
    Column("status", String(20), nullable=False),
    Column("modules", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
)

locations = Table(
    "locations",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column(
        "tenant_id", Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    ),
    Column("name", String(120), nullable=False),
    Column("address", String(500), nullable=False),
    Column("timezone", String(64), nullable=False),
    Column("is_active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
)

whatsapp_numbers = Table(
    "whatsapp_numbers",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column(
        "tenant_id", Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    ),
    Column("phone_number_id", String(32), nullable=False, unique=True),
    Column("display_phone", String(32), nullable=False),
    Column("is_active", Boolean, nullable=False),
    Column("connected_at", DateTime(timezone=True), nullable=False),
)
