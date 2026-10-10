"""FastAPI app factory. `app` is the entrypoint for uvicorn and Vercel (backend/index.py)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap.health import build_health_router
from app.bootstrap.platform import Platform, build_platform
from app.bootstrap.settings import Settings, get_settings
from app.platform.identity.wiring import build_identity_router
from app.platform.jobs.wiring import build_tick_router
from app.platform.messaging.application.commands.statuses import SetCredentials
from app.platform.messaging.presentation.http.routers import (
    build_router as build_credentials_router,
)
from app.shared.infrastructure.logging import configure_logging
from app.shared.module import ModuleDefinition
from app.shared.presentation.errors import register_error_handlers

VERSION = "0.3.0"


def create_app(
    settings: Settings | None = None,
    modules: Sequence[ModuleDefinition] | None = None,
    *,
    platform: Platform | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=not settings.is_local)
    platform = platform or build_platform(settings, modules)
    container = platform.container

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await container.engine.dispose()
        await container.purge_engine.dispose()

    app = FastAPI(title="WhatsApp Automation Platform API", version=VERSION, lifespan=lifespan)
    app.state.platform = platform
    app.state.container = container
    app.state.access_token_verifier = container.access_tokens  # read by shared request_context

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Platform parts that need more than PlatformServices are wired explicitly here.
    app.include_router(build_health_router(container, VERSION))
    app.include_router(
        build_identity_router(platform.identity, secure_cookies=not settings.is_local),
        prefix="/api",
    )
    app.include_router(
        build_credentials_router(SetCredentials(container.credentials)), prefix="/api"
    )
    app.include_router(platform.conversations.webhook_router)
    app.include_router(platform.retention.router, prefix="/api")
    app.include_router(
        build_tick_router(
            container.session_factory,
            container.clock,
            container.job_handlers,
            container.event_handlers,
            settings.cron_secret.get_secret_value(),
            container.jobs,
            {job: hour for module in platform.modules for job, hour in module.daily_jobs.items()},
        )
    )

    # Everything else plugs in through its ModuleDefinition.
    error_status: dict[str, int] = {}
    for module in platform.modules:
        for router in module.build_routers(container):
            app.include_router(router, prefix="/api")
        error_status.update(module.http_error_status)
    register_error_handlers(app, error_status)

    return app


app = create_app()
