"""messages: tenant-owned (RLS). whatsapp_credentials: platform-level, tokens encrypted."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, Integer, String, Table, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB

from app.shared.infrastructure.tables import metadata

messages = Table(
    "messages",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("contact_id", Uuid, nullable=False),
    Column("direction", String(10), nullable=False),
    Column("phone_number_id", String(32), nullable=False),
    Column("wa_message_id", String(128), nullable=True),
    Column("content", JSONB, nullable=False),
    Column("meta", JSONB, nullable=False),
    Column("status", String(20), nullable=False),
    Column("error", Text, nullable=True),
    Column("attempts", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_messages_contact", "tenant_id", "contact_id", "created_at"),
    # Dedupe key for webhook retries; NULL for outbound messages not yet sent.
    Index(
        "uq_messages_wa_message_id",
        "wa_message_id",
        unique=True,
        postgresql_where=text("wa_message_id IS NOT NULL"),
    ),
)

whatsapp_credentials = Table(
    "whatsapp_credentials",
    metadata,
    Column("phone_number_id", String(32), primary_key=True),
    Column("access_token_encrypted", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
)

# A clinic's Meta-approved template per TemplateSlot (PRD PL-4.2). Tenant-owned (RLS).
template_mappings = Table(
    "template_mappings",
    metadata,
    Column("tenant_id", Uuid, primary_key=True),
    Column("slot", String(100), primary_key=True),
    Column("name", String(512), nullable=False),
    Column("language", String(10), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
)
