"""audit_log - tenant-owned (RLS) and append-only (make_append_only in the migration)."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, String, Table, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.shared.infrastructure.tables import metadata

audit_log = Table(
    "audit_log",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("actor_kind", String(20), nullable=False),
    Column("actor_id", Uuid, nullable=True),
    Column("action", String(100), nullable=False),
    Column("resource_type", String(50), nullable=False),
    Column("resource_id", Uuid, nullable=True),
    Column("details", JSONB, nullable=False),
    Column("at", DateTime(timezone=True), nullable=False),
    Index("ix_audit_log_tenant_at", "tenant_id", "at"),
    Index("ix_audit_log_resource", "tenant_id", "resource_type", "resource_id"),
)
