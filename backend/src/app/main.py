"""FastAPI app factory. `app` is the entrypoint for uvicorn and Vercel (backend/index.py)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap.container import Container, build_container
from app.bootstrap.health import build_health_router
from app.bootstrap.modules import INSTALLED_MODULES, PLATFORM_MODULES
from app.bootstrap.settings import Settings, get_settings
from app.platform.identity.wiring import build_identity_router, build_identity_use_cases
from app.platform.jobs.wiring import build_tick_router
from app.platform.tenancy.wiring import build_facade as build_tenancy_facade
from app.shared.infrastructure.logging import configure_logging
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator
from app.shared.module import ModuleDefinition
from app.shared.presentation.errors import register_error_handlers

VERSION = "0.2.0"


def create_app(
    settings: Settings | None = None,
    modules: Sequence[ModuleDefinition] | None = None,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    all_modules = [*PLATFORM_MODULES, *(INSTALLED_MODULES if modules is None else modules)]
    configure_logging(settings.log_level, json=not settings.is_local)
    container = build_container(settings, all_modules, clock=clock, ids=ids)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await container.engine.dispose()

    app = FastAPI(title="WhatsApp Automation Platform API", version=VERSION, lifespan=lifespan)
    app.state.container = container
    app.state.access_token_verifier = container.access_tokens  # read by shared request_context

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(build_health_router(container, VERSION))
    app.include_router(_identity_router(container), prefix="/api")
    app.include_router(
        build_tick_router(
            container.session_factory,
            container.clock,
            container.job_handlers,
            container.event_handlers,
            settings.cron_secret.get_secret_value(),
        )
    )

    error_status: dict[str, int] = {}
    for module in all_modules:
        for router in module.build_routers(container):
            app.include_router(router, prefix="/api")
        error_status.update(module.http_error_status)
    register_error_handlers(app, error_status)

    return app


def _identity_router(container: Container) -> APIRouter:
    use_cases = build_identity_use_cases(
        container,
        hasher=container.password_hasher,
        tokens=container.access_tokens,
        permissions=container.permissions,
        directory=build_tenancy_facade(container),
        refresh_ttl=timedelta(days=container.settings.refresh_token_days),
    )
    return build_identity_router(use_cases, secure_cookies=not container.settings.is_local)


app = create_app()
