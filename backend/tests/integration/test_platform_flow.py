"""End-to-end through HTTP + real PostgreSQL: the onboarding path of a new clinic."""

from __future__ import annotations

import pytest

from app.platform.tenancy.wiring import build_facade
from app.shared.kernel.roles import Role
from tests.integration.conftest import PASSWORD, Api, unique, unique_phone_number_id

pytestmark = pytest.mark.db


async def test_operator_onboards_clinic_and_roles_are_enforced(api: Api) -> None:
    root = await api.login(await api.create_super_admin())

    # Operator creates a tenant and connects its WhatsApp number.
    slug = unique("sunrise")
    created = await api.client.post(
        "/api/platform/tenants",
        json={"name": "Sunrise Clinic", "slug": slug, "modules": ["appointments"]},
        headers=root,
    )
    assert created.status_code == 201, created.text
    tenant_id = created.json()["id"]
    assert created.json()["modules"] == {"appointments": {}}
    phone_number_id = unique_phone_number_id()
    number = await api.client.post(
        f"/api/platform/tenants/{tenant_id}/whatsapp-numbers",
        json={"phone_number_id": phone_number_id, "display_phone": "+91 98765 43210"},
        headers=root,
    )
    assert number.status_code == 201, number.text
    duplicate_slug = await api.client.post(
        "/api/platform/tenants", json={"name": "Copy", "slug": slug}, headers=root
    )
    assert duplicate_slug.status_code == 409
    assert duplicate_slug.json()["code"] == "tenancy.slug_taken"

    # The operator has no tenant selected, so tenant routes are refused.
    assert (await api.client.get("/api/locations", headers=root)).status_code == 403

    # Webhook routing (used in step 3) finds the tenant from Meta's phone_number_id.
    route = await build_facade(api.container).resolve_phone_number_id(phone_number_id)
    assert route is not None
    assert str(route.tenant_id) == tenant_id
    assert route.enabled_modules == {"appointments"}

    # The clinic's first admin (added like the CLI does) manages their own clinic.
    admin_email = await api.add_member(tenant_id, Role.ADMIN)
    admin = await api.login(admin_email)
    me = (await api.client.get("/api/auth/me", headers=admin)).json()
    assert me["active_tenant_id"] == tenant_id
    assert me["memberships"][0]["tenant_name"] == "Sunrise Clinic"
    assert "users.manage" in me["permissions"]

    location = await api.client.post(
        "/api/locations", json={"name": "MG Road", "address": "12 MG Road"}, headers=admin
    )
    assert location.status_code == 201, location.text
    assert location.json()["timezone"] == "Asia/Kolkata"  # inherited from the tenant

    staff_email = f"{unique('staff')}@example.com"
    added = await api.client.post(
        "/api/users",
        json={
            "email": staff_email,
            "full_name": "Front Desk",
            "role": "staff",
            "initial_password": PASSWORD,
        },
        headers=admin,
    )
    assert added.status_code == 201, added.text

    # Staff can read locations but not manage them or the user list.
    staff = await api.login(staff_email)
    assert (await api.client.get("/api/locations", headers=staff)).status_code == 200
    create_as_staff = await api.client.post("/api/locations", json={"name": "X"}, headers=staff)
    assert create_as_staff.status_code == 403
    assert (await api.client.get("/api/users", headers=staff)).status_code == 403

    members = (await api.client.get("/api/users", headers=admin)).json()
    assert {m["email"] for m in members} == {admin_email, staff_email}


async def test_wrong_password_is_401_with_error_code(api: Api) -> None:
    email = await api.create_super_admin()
    response = await api.client.post(
        "/api/auth/login", json={"email": email, "password": "not the password"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "identity.invalid_credentials"
