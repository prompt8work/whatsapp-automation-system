"""Contacts table - tenant-owned, RLS-protected (enable_tenant_rls in the migration)."""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    Uuid,
)

from app.shared.infrastructure.tables import metadata

contacts = Table(
    "contacts",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
    Column("phone_e164", String(16), nullable=False),
    Column("profile_name", String(120), nullable=True),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("last_inbound_at", DateTime(timezone=True), nullable=True),
    Column("consent_given_at", DateTime(timezone=True), nullable=True),
    Column("opted_out_at", DateTime(timezone=True), nullable=True),
    Column("version", Integer, nullable=False),
    UniqueConstraint("tenant_id", "phone_e164", name="uq_contacts_tenant_phone"),
)
