"""Security guarantees that only a real database can prove (PRD G7, AC-10; §11 append-only)."""

from __future__ import annotations

import os
from uuid import UUID

import psycopg
import pytest

from app.platform.contacts.contracts import (
    ResolveContactCommand,
    SearchContactsQuery,
    contacts_for,
)
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role
from tests.integration.conftest import Api

pytestmark = pytest.mark.db


def _raw_dsn() -> str:
    """TEST_DATABASE_URL (role app_rw) in plain psycopg form."""
    return os.environ["TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


async def test_tenants_cannot_see_each_others_contacts(api: Api) -> None:
    root = await api.login(await api.create_super_admin())
    clinic_a = TenantId(UUID(await api.create_tenant(root, "Clinic A")))
    clinic_b = TenantId(UUID(await api.create_tenant(root, "Clinic B")))

    # The same person messages both clinics -> two separate contacts.
    in_a = await contacts_for(api.container, clinic_a).resolve(
        ResolveContactCommand(clinic_a, "919876500001", "Rahul")
    )
    in_b = await contacts_for(api.container, clinic_b).resolve(
        ResolveContactCommand(clinic_b, "919876500001", "Rahul")
    )
    assert in_a.contact.id != in_b.contact.id

    seen_by_a = await contacts_for(api.container, clinic_a).search(
        SearchContactsQuery(clinic_a, Actor.system())
    )
    assert [c.id for c in seen_by_a] == [in_a.contact.id]

    # Via HTTP: a staff member of A asking for B's contact id gets 404, not the data.
    staff_a = await api.login(await api.add_member(str(clinic_a), Role.STAFF))
    response = await api.client.get(f"/api/contacts/{in_b.contact.id}", headers=staff_a)
    assert response.status_code == 404


async def test_rls_fails_closed_without_tenant(api: Api) -> None:
    root = await api.login(await api.create_super_admin())
    clinic = TenantId(UUID(await api.create_tenant(root)))
    await contacts_for(api.container, clinic).resolve(ResolveContactCommand(clinic, "919876500002"))

    # A buggy query that forgets the tenant sees NOTHING (not everything).
    async with await psycopg.AsyncConnection.connect(_raw_dsn()) as conn:
        cur = await conn.execute("SELECT count(*) FROM contacts")
        row = await cur.fetchone()
    assert row == (0,)


async def test_reads_are_audited_and_audit_log_is_append_only(api: Api) -> None:
    root = await api.login(await api.create_super_admin())
    tenant_id = await api.create_tenant(root)
    admin = await api.login(await api.add_member(tenant_id, Role.ADMIN))

    assert (await api.client.get("/api/contacts", headers=admin)).status_code == 200

    entries = (await api.client.get("/api/audit", headers=admin)).json()
    assert entries[0]["action"] == "contact.list"
    assert entries[0]["details"] == {"count": 0, "searched": False}

    async with await psycopg.AsyncConnection.connect(_raw_dsn()) as conn:
        await conn.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant_id,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute("UPDATE audit_log SET action = 'tampered'")


async def test_refresh_cookie_rotation_and_reuse_detection(api: Api) -> None:
    root_email = await api.create_super_admin()
    login = await api.client.post(
        "/api/auth/login", json={"email": root_email, "password": "integration-password-1"}
    )
    first_cookie = login.cookies["refresh_token"]
    assert "httponly" in login.headers["set-cookie"].lower()
    assert "path=/api/auth" in login.headers["set-cookie"].lower()

    refreshed = await api.client.post("/api/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.cookies["refresh_token"] != first_cookie

    # Replay the first (already rotated) cookie: rejected, and the whole session dies.
    newest_cookie = refreshed.cookies["refresh_token"]
    api.client.cookies.clear()
    api.client.cookies.set("refresh_token", first_cookie)
    replay = await api.client.post("/api/auth/refresh")
    assert replay.status_code == 401

    api.client.cookies.clear()
    api.client.cookies.set("refresh_token", newest_cookie)
    after = await api.client.post("/api/auth/refresh")
    assert after.status_code == 401
