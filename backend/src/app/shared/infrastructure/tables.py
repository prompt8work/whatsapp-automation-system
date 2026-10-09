"""Shared SQLAlchemy metadata and platform-wide tables.

Every module defines its tables on THIS `metadata` (in its own infrastructure/tables.py)
so Alembic sees one schema. Naming convention keeps constraint names stable for migrations.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, Integer, MetaData, String, Table, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

# Transactional outbox (ARCHITECTURE §8.4). Written in the same transaction as the state
# change; a dispatcher delivers rows after commit, the cron tick re-delivers stragglers.
outbox = Table(
    "outbox",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=True),  # NULL for platform-level events
    Column("event_type", String(200), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("dispatched_at", DateTime(timezone=True), nullable=True),
    # Delivery bookkeeping (platform/jobs DispatchOutbox):
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("next_attempt_at", DateTime(timezone=True), nullable=True),
    Column("last_error", Text, nullable=True),
    Column("dead_at", DateTime(timezone=True), nullable=True),
    Index(
        "ix_outbox_undispatched",
        "created_at",
        postgresql_where=text("dispatched_at IS NULL"),
    ),
)
