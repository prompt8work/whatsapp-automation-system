"""conversation_sessions - tenant-owned (RLS), one row per contact."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, Table, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.shared.infrastructure.tables import metadata

conversation_sessions = Table(
    "conversation_sessions",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("contact_id", Uuid, nullable=False),
    Column("flow_key", String(100), nullable=True),
    Column("step_key", String(100), nullable=True),
    Column("last_flow_key", String(100), nullable=True),
    Column("data", JSONB, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("tenant_id", "contact_id", name="uq_conversation_sessions_contact"),
)
