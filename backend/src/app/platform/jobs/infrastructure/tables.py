"""scheduled_jobs - platform-level (no RLS): the runner works across tenants."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, Integer, String, Table, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB

from app.shared.infrastructure.tables import metadata

scheduled_jobs = Table(
    "scheduled_jobs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("job_type", String(100), nullable=False),
    Column("tenant_id", Uuid, nullable=True),
    Column("run_at", DateTime(timezone=True), nullable=False),
    Column("idempotency_key", String(200), nullable=False, unique=True),
    Column("payload", JSONB, nullable=False),
    Column("max_attempts", Integer, nullable=False),
    Column("status", String(20), nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("last_error", Text, nullable=True),
    Column("locked_until", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Index(
        "ix_scheduled_jobs_due",
        "run_at",
        postgresql_where=text("status IN ('pending', 'running')"),
    ),
)
