"""deletion_records - tenant-owned (RLS), append-only. No personal data (PRD AP-10.5)."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, String, Table, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.shared.infrastructure.tables import metadata

deletion_records = Table(
    "deletion_records",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("purger", String(60), nullable=False),
    Column("subject_type", String(30), nullable=False),
    Column("subject_id", Uuid, nullable=False),
    Column("rule", String(20), nullable=False),
    Column("counts", JSONB, nullable=False),
    Column("at", DateTime(timezone=True), nullable=False),
    Index("ix_deletion_records_tenant_at", "tenant_id", "at"),
)
