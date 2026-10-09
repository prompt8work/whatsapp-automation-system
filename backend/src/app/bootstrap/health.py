"""Liveness and readiness endpoints (System status page, uptime checks)."""

from __future__ import annotations

from typing import Literal

import structlog
from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.bootstrap.container import Container

log = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    environment: str
    version: str


def build_health_router(container: Container, version: str) -> APIRouter:
    router = APIRouter(prefix="/api/health", tags=["system"])
    env = container.settings.environment

    @router.get("", response_model=HealthResponse)
    async def liveness() -> HealthResponse:
        """The process is up. Does not touch the database."""
        return HealthResponse(status="ok", environment=env, version=version)

    @router.get(
        "/ready",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse}},
    )
    async def readiness(response: Response) -> HealthResponse:
        """The process can reach the database."""
        try:
            async with container.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            log.warning("readiness.db_unreachable", exc_info=True)
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthResponse(status="unavailable", environment=env, version=version)
        return HealthResponse(status="ok", environment=env, version=version)

    return router
