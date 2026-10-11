"""Payments tables - tenant-owned (RLS). payment_events is append-only. Payments are never
deleted (RT-7): no foreign keys to contacts or to any module's records."""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.shared.infrastructure.tables import metadata

TS = DateTime(timezone=True)

payments = Table(
    "payments",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("receipt_number", String(16), nullable=False),
    Column("subject_type", String(40), nullable=True),
    Column("subject_id", Uuid, nullable=True),
    Column("contact_id", Uuid, nullable=True),
    Column("payer_name", String(120), nullable=False),
    Column("payer_phone", String(16), nullable=False),
    Column("purpose", String(120), nullable=False),
    Column("amount_minor", Integer, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("method", String(20), nullable=False),
    Column("status", String(10), nullable=False),
    Column("created_at", TS, nullable=False),
    Column("expires_at", TS, nullable=True),
    Column("gateway_ref", String(64), nullable=True),
    Column("pay_url", Text, nullable=True),
    Column("transaction_id", String(64), nullable=True),
    Column("paid_at", TS, nullable=True),
    Column("refunded_at", TS, nullable=True),
    Column("note", String(200), nullable=False),
    Column("version", Integer, nullable=False),
    UniqueConstraint("tenant_id", "receipt_number", name="uq_payments_receipt"),
    Index("ix_payments_subject", "tenant_id", "subject_type", "subject_id"),
    Index("ix_payments_status", "tenant_id", "status", "created_at"),
    Index(
        "ix_payments_gateway_ref",
        "gateway_ref",
        postgresql_where=text("gateway_ref IS NOT NULL"),
    ),
)

payment_events = Table(
    "payment_events",
    metadata,
    Column("id", Uuid, primary_key=True),  # = DomainEvent.event_id
    Column("tenant_id", Uuid, nullable=False),
    Column("payment_id", Uuid, ForeignKey("payments.id"), nullable=False),
    Column("event_type", String(40), nullable=False),
    Column("actor", String(60), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("occurred_at", TS, nullable=False),
    Index("ix_payment_events_payment", "payment_id", "occurred_at"),
)

# One row per tenant. Razorpay secrets are Fernet-encrypted (CREDENTIALS_KEY).
payment_settings = Table(
    "payment_settings",
    metadata,
    Column("tenant_id", Uuid, primary_key=True),
    Column("methods", JSONB, nullable=False),
    Column("whatsapp_pay_configuration", String(100), nullable=False),
    Column("razorpay_key_id", String(64), nullable=False),
    Column("razorpay_key_secret_encrypted", Text, nullable=True),
    Column("razorpay_webhook_secret_encrypted", Text, nullable=True),
    Column("updated_at", TS, nullable=False, server_default=text("now()")),
)
