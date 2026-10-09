"""Real JWTs + real request_context dependencies (no database)."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated
from uuid import UUID

import httpx
import jwt
import pytest
from fastapi import Depends, FastAPI

from app.platform.identity.infrastructure.tokens import JwtAccessTokens
from app.shared.application.auth import InvalidAccessTokenError, Principal
from app.shared.application.permissions import PermissionRegistry
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role
from app.shared.presentation.request_context import (
    RequestContext,
    require,
    require_super_admin,
)
from app.shared.testing.fakes import FixedClock

SECRET = "x" * 40
CLINIC = TenantId(UUID(int=5))


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def tokens(clock: FixedClock) -> JwtAccessTokens:
    registry = PermissionRegistry()
    registry.register({"contact.read": "", "users.manage": ""}, {Role.STAFF: {"contact.read"}})
    return JwtAccessTokens(SECRET, timedelta(minutes=15), clock, registry)


def principal(role: Role | None, tenant: TenantId | None = CLINIC, sa: bool = False) -> Principal:
    return Principal(UUID(int=1), tenant, role, is_super_admin=sa)


def test_round_trip_derives_permissions_from_role(tokens: JwtAccessTokens) -> None:
    verified = tokens.verify(tokens.issue(principal(Role.STAFF)).token)

    assert verified.tenant_id == CLINIC
    assert verified.permissions == {"contact.read"}


def test_admin_gets_every_permission(tokens: JwtAccessTokens) -> None:
    verified = tokens.verify(tokens.issue(principal(Role.ADMIN)).token)
    assert verified.permissions == {"contact.read", "users.manage"}


def test_expired_token_rejected(tokens: JwtAccessTokens, clock: FixedClock) -> None:
    token = tokens.issue(principal(Role.STAFF)).token
    clock.advance(timedelta(minutes=16))
    with pytest.raises(InvalidAccessTokenError):
        tokens.verify(token)


def test_token_signed_with_other_secret_rejected(tokens: JwtAccessTokens) -> None:
    forged = jwt.encode({"sub": str(UUID(int=1)), "iss": "wa-platform", "exp": 9e9}, "y" * 40)
    with pytest.raises(InvalidAccessTokenError):
        tokens.verify(forged)


@pytest.fixture
def client(tokens: JwtAccessTokens) -> httpx.AsyncClient:
    app = FastAPI()
    app.state.access_token_verifier = tokens

    @app.get("/contacts")
    async def contacts(ctx: Annotated[RequestContext, Depends(require("contact.read"))]) -> str:
        return str(ctx.tenant_id)

    @app.get("/platform")
    async def platform(p: Annotated[Principal, Depends(require_super_admin)]) -> str:
        return "ok"

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def bearer(tokens: JwtAccessTokens, p: Principal) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens.issue(p).token}"}


async def test_route_permissions(client: httpx.AsyncClient, tokens: JwtAccessTokens) -> None:
    assert (await client.get("/contacts")).status_code == 401
    assert (
        await client.get("/contacts", headers={"Authorization": "Bearer junk"})
    ).status_code == 401
    assert (
        await client.get("/contacts", headers=bearer(tokens, principal(Role.DOCTOR)))
    ).status_code == 403
    ok = await client.get("/contacts", headers=bearer(tokens, principal(Role.STAFF)))
    assert ok.status_code == 200
    assert ok.json() == str(CLINIC)
    no_tenant = await client.get("/contacts", headers=bearer(tokens, principal(None, tenant=None)))
    assert no_tenant.status_code == 403


async def test_platform_routes_need_super_admin(
    client: httpx.AsyncClient, tokens: JwtAccessTokens
) -> None:
    assert (
        await client.get("/platform", headers=bearer(tokens, principal(Role.ADMIN)))
    ).status_code == 403
    operator = principal(None, tenant=None, sa=True)
    assert (await client.get("/platform", headers=bearer(tokens, operator))).status_code == 200
