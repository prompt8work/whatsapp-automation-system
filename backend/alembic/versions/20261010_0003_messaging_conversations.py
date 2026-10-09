"""messaging + conversations: message log, encrypted credentials, sessions

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-10

Tenant-owned (RLS): messages, conversation_sessions. Platform-level: whatsapp_credentials.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.shared.infrastructure.migrations import disable_tenant_rls, enable_tenant_rls

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("phone_number_id", sa.String(32), nullable=False),
        sa.Column("wa_message_id", sa.String(128), nullable=True),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("meta", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_messages_contact", "messages", ["tenant_id", "contact_id", "created_at"])
    op.create_index(
        "uq_messages_wa_message_id",
        "messages",
        ["wa_message_id"],
        unique=True,
        postgresql_where=sa.text("wa_message_id IS NOT NULL"),
    )
    enable_tenant_rls("messages")

    op.create_table(
        "whatsapp_credentials",
        sa.Column("phone_number_id", sa.String(32), primary_key=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "conversation_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("flow_key", sa.String(100), nullable=True),
        sa.Column("step_key", sa.String(100), nullable=True),
        sa.Column("last_flow_key", sa.String(100), nullable=True),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", TS, nullable=True),
        sa.Column("updated_at", TS, nullable=False),
        sa.UniqueConstraint("tenant_id", "contact_id", name="uq_conversation_sessions_contact"),
    )
    enable_tenant_rls("conversation_sessions")


def downgrade() -> None:
    disable_tenant_rls("conversation_sessions")
    op.drop_table("conversation_sessions")
    op.drop_table("whatsapp_credentials")
    disable_tenant_rls("messages")
    op.drop_index("uq_messages_wa_message_id", table_name="messages")
    op.drop_index("ix_messages_contact", table_name="messages")
    op.drop_table("messages")
