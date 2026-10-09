"""Composition root (ADR-002): build every concrete adapter ONCE, by hand, no DI framework.

To swap an implementation (e.g. a fake WhatsApp sender locally) change it HERE -
use cases only see Protocols and never notice.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.bootstrap.settings import Settings
from app.platform.audit.infrastructure.sql import SqlAuditLogger
from app.platform.identity.infrastructure.passwords import Argon2PasswordHasher
from app.platform.identity.infrastructure.tokens import JwtAccessTokens
from app.platform.jobs.application.registry import EventHandlerRegistry, JobHandlerRegistry
from app.platform.jobs.infrastructure.scheduler import SqlJobScheduler
from app.shared.application.audit import AuditLogger
from app.shared.application.jobs import JobScheduler
from app.shared.application.permissions import PermissionRegistry
from app.shared.infrastructure.db import create_engine, create_session_factory
from app.shared.kernel.clock import Clock, SystemClock
from app.shared.kernel.ids import IdGenerator, Uuid7Generator
from app.shared.module import ModuleDefinition


@dataclass(frozen=True)
class Container:
    """Implements `app.shared.module.PlatformServices` (and holds platform-only extras)."""

    settings: Settings
    clock: Clock
    ids: IdGenerator
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    audit: AuditLogger
    jobs: JobScheduler
    permissions: PermissionRegistry
    password_hasher: Argon2PasswordHasher
    access_tokens: JwtAccessTokens
    job_handlers: JobHandlerRegistry
    event_handlers: EventHandlerRegistry


def build_container(
    settings: Settings,
    modules: Sequence[ModuleDefinition],
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
) -> Container:
    clock = clock or SystemClock()
    ids = ids or Uuid7Generator()
    engine = create_engine(settings.database_url)  # lazy: connects on first use
    session_factory = create_session_factory(engine)

    permissions = PermissionRegistry()
    for module in modules:
        permissions.register(module.permissions, module.role_grants)

    container = Container(
        settings=settings,
        clock=clock,
        ids=ids,
        engine=engine,
        session_factory=session_factory,
        audit=SqlAuditLogger(session_factory, clock, ids),
        jobs=SqlJobScheduler(session_factory, clock, ids),
        permissions=permissions,
        password_hasher=Argon2PasswordHasher(),
        access_tokens=JwtAccessTokens(
            settings.jwt_secret.get_secret_value(),
            timedelta(minutes=settings.access_token_minutes),
            clock,
            permissions,
        ),
        job_handlers=JobHandlerRegistry(),
        event_handlers=EventHandlerRegistry(),
    )

    # Handlers need the finished container (they receive PlatformServices).
    for module in modules:
        for job_type, make_job_handler in module.job_handlers.items():
            container.job_handlers.register(job_type, make_job_handler(container))
        for event_type, factories in module.event_handlers.items():
            for make_event_handler in factories:
                container.event_handlers.register(event_type, make_event_handler(container))
    return container
