"""Helpers for Alembic migrations. Use these instead of hand-writing the SQL each time.

from app.shared.infrastructure.migrations import enable_tenant_rls, make_append_only

def upgrade() -> None:
    op.create_table("appointments", ...)
    enable_tenant_rls("appointments")
"""

from __future__ import annotations

from alembic import op

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def enable_tenant_rls(table: str) -> None:
    """Row-level security on `tenant_id` (ARCHITECTURE §8.2, ADR-004).

    FORCE makes the policy apply to the table owner as well. When `app.tenant_id` is not
    set the expression is NULL, so NO rows are visible - failing closed, not open.
    """
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (tenant_id = {_TENANT}) WITH CHECK (tenant_id = {_TENANT})"
    )


def disable_tenant_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def make_append_only(table: str) -> None:
    """History/event tables: the API role may only INSERT (PRD §11). Purges use app_purge."""
    op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM app_rw")
