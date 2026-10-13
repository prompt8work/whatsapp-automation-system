"""Builds the whole platform once. Used by the HTTP app (main.py), the CLI and the tests,
so all three are wired identically."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

import httpx

from app.bootstrap.container import Container, build_container
from app.bootstrap.modules import INSTALLED_MODULES, PLATFORM_MODULES
from app.bootstrap.settings import Settings
from app.platform.conversations.application.handle_webhook import PROCESS_JOB
from app.platform.conversations.wiring import Conversations, build_conversations
from app.platform.identity.application.use_cases import IdentityUseCases
from app.platform.identity.wiring import build_identity_use_cases
from app.platform.inbox.wiring import InboxHandoverDesk
from app.platform.messaging.application.ports import WhatsAppGateway
from app.platform.payments.wiring import WhatsAppPaymentSink
from app.platform.retention.application.use_cases import RUN_JOB as RETENTION_JOB
from app.platform.retention.wiring import Retention, build_retention
from app.platform.tenancy.contracts import TenancyFacade
from app.platform.tenancy.wiring import build_facade
from app.shared.application.jobs import JobScheduler
from app.shared.application.understanding import Understanding
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator
from app.shared.module import ModuleDefinition


@dataclass(frozen=True)
class Platform:
    container: Container
    modules: list[ModuleDefinition]
    tenancy: TenancyFacade
    identity: IdentityUseCases
    conversations: Conversations
    retention: Retention


def build_platform(
    settings: Settings,
    feature_modules: Sequence[ModuleDefinition] | None = None,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
    whatsapp_gateway: WhatsAppGateway | None = None,
    http_client: httpx.AsyncClient | None = None,
    understanding: Understanding | None = None,
    jobs: JobScheduler | None = None,
) -> Platform:
    modules = [
        *PLATFORM_MODULES,
        *(INSTALLED_MODULES if feature_modules is None else feature_modules),
    ]
    container = build_container(
        settings,
        modules,
        clock=clock,
        ids=ids,
        whatsapp_gateway=whatsapp_gateway,
        http_client=http_client,
        understanding=understanding,
        jobs=jobs,
    )
    tenancy = build_facade(container)
    identity = build_identity_use_cases(
        container,
        hasher=container.password_hasher,
        tokens=container.access_tokens,
        permissions=container.permissions,
        directory=tenancy,
        refresh_ttl=timedelta(days=settings.refresh_token_days),
    )
    conversations = build_conversations(
        container,
        modules,
        tenancy,
        verify_token=settings.meta_verify_token.get_secret_value(),
        app_secret=settings.meta_app_secret.get_secret_value(),
        require_signature=not settings.is_local,
        handover=InboxHandoverDesk(container),
        payments=WhatsAppPaymentSink(container.payments_core),
    )
    container.job_handlers.register(PROCESS_JOB, conversations.process_job)
    retention = build_retention(container, modules)
    container.job_handlers.register(RETENTION_JOB, retention.run.handle)
    return Platform(container, modules, tenancy, identity, conversations, retention)
