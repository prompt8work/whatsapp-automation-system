"""HTTP tests: real router + real error mapping, fake Unit of Work (no database)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from app.modules._template.application.commands.create_item import CreateItem
from app.modules._template.application.commands.rename_item import RenameItem
from app.modules._template.application.queries.get_item import GetItem
from app.modules._template.application.use_cases import ItemUseCases
from app.modules._template.presentation.http.routers import HTTP_ERROR_STATUS, build_router
from app.modules._template.tests.fakes import InMemoryTemplateUnitOfWork
from app.shared.application.auth import Principal
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role
from app.shared.presentation.errors import register_error_handlers
from app.shared.presentation.request_context import RequestContext, get_request_context
from app.shared.testing.fakes import FixedClock, SequentialIds

TENANT = TenantId(UUID(int=100))


def signed_in(*permissions: str) -> RequestContext:
    """Skip real JWTs in HTTP tests: override the dependency with a ready-made context."""
    principal = Principal(UUID(int=7), TENANT, Role.STAFF, permissions=frozenset(permissions))
    return RequestContext(tenant_id=TENANT, principal=principal)


@pytest.fixture
def app() -> FastAPI:
    uow, clock, ids = InMemoryTemplateUnitOfWork(), FixedClock(), SequentialIds()

    def use_cases_for(tenant_id: TenantId) -> ItemUseCases:
        return ItemUseCases(
            create=CreateItem(uow, clock, ids, tenant_id),
            rename=RenameItem(uow, clock),
            get=GetItem(uow),
        )

    app = FastAPI()
    app.include_router(build_router(use_cases_for), prefix="/api")
    register_error_handlers(app, HTTP_ERROR_STATUS)
    app.dependency_overrides[get_request_context] = lambda: signed_in(
        "template.item.read", "template.item.write"
    )
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_create_get_rename_round_trip(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/template/items", json={"name": "Hi"})
    assert created.status_code == 201
    item_id = created.json()["id"]

    renamed = await client.patch(f"/api/template/items/{item_id}", json={"name": "Hello"})
    fetched = await client.get(f"/api/template/items/{item_id}")

    assert renamed.status_code == 200
    assert fetched.json()["name"] == "Hello"


async def test_domain_error_is_mapped_to_status_and_code(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/template/items", json={"name": "Same"})
    item_id = created.json()["id"]

    response = await client.patch(f"/api/template/items/{item_id}", json={"name": "Same"})

    assert response.status_code == 409
    assert response.json()["code"] == "template.name_unchanged"


async def test_missing_permission_is_forbidden(app: FastAPI, client: httpx.AsyncClient) -> None:
    app.dependency_overrides[get_request_context] = lambda: signed_in("template.item.read")

    response = await client.post("/api/template/items", json={"name": "Hi"})

    assert response.status_code == 403
