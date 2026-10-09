"""Fixtures for tests against a REAL PostgreSQL (marked `db`, skipped without TEST_DATABASE_URL).

Expects the database to be migrated (`alembic upgrade head`) with the roles from
infra/postgres/init.sql. TEST_DATABASE_URL must use role app_rw so RLS is really enforced.
Tests isolate themselves with unique slugs/emails instead of truncating tables.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr

from app.bootstrap.container import Container
from app.bootstrap.settings import Settings
from app.main import create_app
from app.platform.identity.application.commands.create_user import CreateUserCommand
from app.platform.identity.application.commands.members import AddMemberCommand
from app.platform.identity.application.use_cases import IdentityUseCases
from app.platform.identity.wiring import build_identity_use_cases
from app.platform.tenancy.wiring import build_facade
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role
from app.shared.module import ModuleDefinition

PASSWORD = "integration-password-1"
CRON_SECRET = "integration-cron-secret"


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def unique_phone_number_id() -> str:
    return str(uuid.uuid4().int)[:15]


@dataclass
class Api:
    app: FastAPI
    client: httpx.AsyncClient

    @property
    def container(self) -> Container:
        container: Container = self.app.state.container
        return container

    async def login(self, email: str, tenant_id: str | None = None) -> dict[str, str]:
        body = {"email": email, "password": PASSWORD, "tenant_id": tenant_id}
        response = await self.client.post("/api/auth/login", json=body)
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    @property
    def identity(self) -> IdentityUseCases:
        c = self.container
        return build_identity_use_cases(
            c,
            hasher=c.password_hasher,
            tokens=c.access_tokens,
            permissions=c.permissions,
            directory=build_facade(c),
            refresh_ttl=timedelta(days=1),
        )

    async def create_super_admin(self) -> str:
        """Like `cli create-superadmin`."""
        email = f"{unique('root')}@example.com"
        await self.identity.create_user(
            CreateUserCommand(email, "Root", PASSWORD, Actor.system(), is_super_admin=True)
        )
        return email

    async def add_member(self, tenant_id: str, role: Role, email: str | None = None) -> str:
        """Like `cli add-member`."""
        email = email or f"{unique(role.value)}@example.com"
        await self.identity.add_member(
            AddMemberCommand(
                TenantId(uuid.UUID(tenant_id)), email, "Member", role, Actor.system(), PASSWORD
            )
        )
        return email

    async def create_tenant(self, root: dict[str, str], name: str = "Clinic") -> str:
        response = await self.client.post(
            "/api/platform/tenants",
            json={"name": name, "slug": unique("clinic"), "modules": ["appointments"]},
            headers=root,
        )
        assert response.status_code == 201, response.text
        tenant_id: str = response.json()["id"]
        return tenant_id


ApiFactory = Callable[..., Awaitable[Api]]


@pytest.fixture
async def make_api() -> AsyncIterator[ApiFactory]:
    """Build an Api with extra feature modules / settings: `await make_api(modules=[...])`."""
    apps: list[FastAPI] = []
    clients: list[httpx.AsyncClient] = []

    async def factory(
        modules: Sequence[ModuleDefinition] | None = None, **settings_overrides: Any
    ) -> Api:
        settings = Settings(
            environment="test",
            database_url=os.environ["TEST_DATABASE_URL"],
            cron_secret=SecretStr(CRON_SECRET),
            **settings_overrides,
        )
        app = create_app(settings, modules)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        )
        apps.append(app)
        clients.append(client)
        return Api(app, client)

    yield factory
    for client in clients:
        await client.aclose()
    for app in apps:
        await app.state.container.engine.dispose()


@pytest.fixture
async def api(make_api: ApiFactory) -> Api:
    return await make_api()
