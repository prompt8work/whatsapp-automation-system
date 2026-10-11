"""Composition root (ADR-002): build every concrete adapter ONCE, by hand, no DI framework.

To swap an implementation (e.g. the WhatsApp gateway) change it HERE - use cases only see
Protocols and never notice.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.bootstrap.settings import Settings
from app.platform.audit.infrastructure.sql import SqlAuditLogger
from app.platform.identity.infrastructure.passwords import Argon2PasswordHasher
from app.platform.identity.infrastructure.tokens import JwtAccessTokens
from app.platform.jobs.application.registry import EventHandlerRegistry, JobHandlerRegistry
from app.platform.jobs.infrastructure.scheduler import SqlJobScheduler
from app.platform.messaging.application.commands.send_message import RETRY_JOB
from app.platform.messaging.application.ports import WhatsAppGateway
from app.platform.messaging.domain.repositories import CredentialStore
from app.platform.messaging.infrastructure.meta import MetaCloudGateway
from app.platform.messaging.infrastructure.recording import RecordingGateway
from app.platform.messaging.infrastructure.repositories import (
    LocalCredentialStore,
    SqlCredentialStore,
)
from app.platform.messaging.wiring import TenantMessenger
from app.platform.payments.application.use_cases import EXPIRE_JOB as PAYMENT_EXPIRE_JOB
from app.platform.payments.contracts import PaymentsFacade
from app.platform.payments.wiring import PaymentsCore, build_payments_core
from app.platform.understanding.infrastructure.claude import ClaudeUnderstanding
from app.shared.application.audit import AuditLogger
from app.shared.application.jobs import JobScheduler
from app.shared.application.permissions import PermissionRegistry
from app.shared.application.understanding import NoUnderstanding, Understanding
from app.shared.infrastructure.db import create_engine, create_session_factory
from app.shared.infrastructure.live import register_live_topics
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
    purge_engine: AsyncEngine
    purge_session_factory: async_sessionmaker[AsyncSession]
    audit: AuditLogger
    jobs: JobScheduler
    messenger: TenantMessenger
    whatsapp_gateway: WhatsAppGateway
    credentials: CredentialStore
    permissions: PermissionRegistry
    password_hasher: Argon2PasswordHasher
    access_tokens: JwtAccessTokens
    job_handlers: JobHandlerRegistry
    event_handlers: EventHandlerRegistry
    payments_core: PaymentsCore
    understanding: Understanding

    @property
    def payments(self) -> PaymentsFacade:
        return self.payments_core.facade


def _whatsapp(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> tuple[WhatsAppGateway, CredentialStore]:
    if settings.whatsapp_sender == "meta":
        return (
            MetaCloudGateway(httpx.AsyncClient(), settings.meta_graph_api_version),
            SqlCredentialStore(session_factory, settings.credentials_key.get_secret_value()),
        )
    return RecordingGateway(), LocalCredentialStore()


def build_container(
    settings: Settings,
    modules: Sequence[ModuleDefinition],
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    whatsapp_gateway: WhatsAppGateway | None = None,
    http_client: httpx.AsyncClient | None = None,
    understanding: Understanding | None = None,
) -> Container:
    clock = clock or SystemClock()
    ids = ids or Uuid7Generator()
    engine = create_engine(settings.database_url)  # lazy: connects on first use
    session_factory = create_session_factory(engine)
    purge_engine = create_engine(settings.database_purge_url)

    permissions = PermissionRegistry()
    for module in modules:
        permissions.register(module.permissions, module.role_grants)
        register_live_topics(module.live_topics)

    gateway, credentials = _whatsapp(settings, session_factory)
    gateway = whatsapp_gateway or gateway
    jobs = SqlJobScheduler(session_factory, clock, ids)
    messenger = TenantMessenger(session_factory, gateway, credentials, jobs, clock, ids)
    audit = SqlAuditLogger(session_factory, clock, ids)
    http = http_client or httpx.AsyncClient(timeout=15)
    if understanding is None and settings.llm_provider == "anthropic":
        understanding = ClaudeUnderstanding(
            http, settings.anthropic_api_key.get_secret_value(), settings.llm_model
        )
    payments_core = build_payments_core(
        session_factory,
        credentials_key=settings.credentials_key.get_secret_value(),
        http_client=http,
        jobs=jobs,
        audit=audit,
        clock=clock,
        ids=ids,
    )

    container = Container(
        settings=settings,
        clock=clock,
        ids=ids,
        engine=engine,
        session_factory=session_factory,
        purge_engine=purge_engine,
        purge_session_factory=create_session_factory(purge_engine),
        audit=audit,
        jobs=jobs,
        messenger=messenger,
        whatsapp_gateway=gateway,
        credentials=credentials,
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
        payments_core=payments_core,
        understanding=understanding or NoUnderstanding(),
    )

    container.job_handlers.register(RETRY_JOB, messenger.retry_handler())
    container.job_handlers.register(PAYMENT_EXPIRE_JOB, payments_core.expire_job())
    # Module handlers need the finished container (they receive PlatformServices).
    for module in modules:
        for job_type, make_job_handler in module.job_handlers.items():
            container.job_handlers.register(job_type, make_job_handler(container))
        for event_type, factories in module.event_handlers.items():
            for make_event_handler in factories:
                container.event_handlers.register(event_type, make_event_handler(container))
    return container
