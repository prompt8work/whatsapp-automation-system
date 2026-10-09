"""Identity tables. Platform-level (no RLS): users exist across tenants. Only this module's
repositories touch them, always filtering by user id / email / token hash explicitly."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Uuid,
)

from app.shared.infrastructure.tables import metadata

users = Table(
    "users",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("email", String(254), nullable=False, unique=True),
    Column("full_name", String(200), nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("is_super_admin", Boolean, nullable=False, default=False),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
)

memberships = Table(
    "memberships",
    metadata,
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("tenant_id", Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True),
    Column("role", String(20), nullable=False),
    Index("ix_memberships_tenant_id", "tenant_id"),
)

refresh_sessions = Table(
    "refresh_sessions",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("family_id", Uuid, nullable=False, index=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("active_tenant_id", Uuid, nullable=True),
    Column("issued_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("replaced_by", Uuid, nullable=True),
)
