"""platform foundations: tenancy, identity, contacts, audit, jobs

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-10

Platform-level tables (no RLS): tenants, whatsapp_numbers, users, memberships,
refresh_sessions, scheduled_jobs. Tenant-owned (RLS): locations, contacts, audit_log.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.shared.infrastructure.migrations import (
    disable_tenant_rls,
    enable_tenant_rls,
    make_append_only,
)

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    # ------------------------------------------------------------------ tenancy
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(40), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("modules", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_locations_tenant_id", "locations", ["tenant_id"])
    enable_tenant_rls("locations")

    op.create_table(
        "whatsapp_numbers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("phone_number_id", sa.String(32), nullable=False),
        sa.Column("display_phone", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("connected_at", TS, nullable=False),
        sa.UniqueConstraint("phone_number_id", name="uq_whatsapp_numbers_phone_number_id"),
    )
    op.create_index("ix_whatsapp_numbers_tenant_id", "whatsapp_numbers", ["tenant_id"])

    # ------------------------------------------------------------------ identity
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_super_admin", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "memberships",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(20), nullable=False),
    )
    op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"])
    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("active_tenant_id", sa.Uuid(), nullable=True),
        sa.Column("issued_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS, nullable=True),
        sa.Column("replaced_by", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_refresh_sessions_token_hash"),
    )
    op.create_index("ix_refresh_sessions_family_id", "refresh_sessions", ["family_id"])

    # ------------------------------------------------------------------ contacts
    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("phone_e164", sa.String(16), nullable=False),
        sa.Column("profile_name", sa.String(120), nullable=True),
        sa.Column("first_seen_at", TS, nullable=False),
        sa.Column("last_inbound_at", TS, nullable=True),
        sa.Column("consent_given_at", TS, nullable=True),
        sa.Column("opted_out_at", TS, nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "phone_e164", name="uq_contacts_tenant_phone"),
    )
    enable_tenant_rls("contacts")

    # ------------------------------------------------------------------ audit
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("actor_kind", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("at", TS, nullable=False),
    )
    op.create_index("ix_audit_log_tenant_at", "audit_log", ["tenant_id", "at"])
    op.create_index(
        "ix_audit_log_resource", "audit_log", ["tenant_id", "resource_type", "resource_id"]
    )
    enable_tenant_rls("audit_log")
    make_append_only("audit_log")

    # ------------------------------------------------------------------ jobs
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("run_at", TS, nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("locked_until", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("finished_at", TS, nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_scheduled_jobs_idempotency_key"),
    )
    op.create_index(
        "ix_scheduled_jobs_due",
        "scheduled_jobs",
        ["run_at"],
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )

    op.add_column("outbox", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("outbox", sa.Column("next_attempt_at", TS, nullable=True))
    op.add_column("outbox", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("outbox", sa.Column("dead_at", TS, nullable=True))


def downgrade() -> None:
    for column in ("dead_at", "last_error", "next_attempt_at", "attempts"):
        op.drop_column("outbox", column)
    op.drop_table("scheduled_jobs")
    disable_tenant_rls("audit_log")
    op.drop_table("audit_log")
    disable_tenant_rls("contacts")
    op.drop_table("contacts")
    op.drop_table("refresh_sessions")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("whatsapp_numbers")
    disable_tenant_rls("locations")
    op.drop_table("locations")
    op.drop_table("tenants")
