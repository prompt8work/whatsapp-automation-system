"""SQLAlchemy table definitions on the shared metadata.

Every tenant-owned table has `tenant_id` and gets RLS in its migration:
`enable_tenant_rls("template_items")` (app/shared/infrastructure/migrations.py).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, Table, Uuid

from app.shared.infrastructure.tables import metadata

template_items = Table(
    "template_items",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False, index=True),
    Column("name", String(100), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
)
