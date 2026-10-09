"""App factory: health endpoints and module installation."""

from __future__ import annotations

import httpx

from app.bootstrap.settings import Settings
from app.main import create_app
from app.modules._template.module import module as template_module

UNREACHABLE_DB = "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none"


def client_for(settings: Settings, **kwargs: object) -> httpx.AsyncClient:
    app = create_app(settings, **kwargs)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_liveness_does_not_need_database() -> None:
    async with client_for(Settings(environment="test", database_url=UNREACHABLE_DB)) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness_reports_unavailable_database() -> None:
    async with client_for(Settings(environment="test", database_url=UNREACHABLE_DB)) as client:
        response = await client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"


async def test_installed_module_routes_are_mounted_under_api() -> None:
    settings = Settings(environment="test", database_url=UNREACHABLE_DB)
    async with client_for(settings, modules=[template_module]) as client:
        schema = (await client.get("/openapi.json")).json()

    assert "/api/template/items" in schema["paths"]
