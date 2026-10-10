"""Conversations wiring: adapters from the pipeline's ports to the real modules, and the
builder bootstrap calls once at startup."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter

from app.platform.contacts.contracts import (
    GrantConsentCommand,
    ResolveContactCommand,
    SetOptOutCommand,
)
from app.platform.contacts.integration import contacts_for
from app.platform.conversations.application.engine import FlowEngine, FlowRegistry, Router
from app.platform.conversations.application.handle_inbound import HandleInboundMessage
from app.platform.conversations.application.handle_webhook import HandleWebhook, ProcessInboundJob
from app.platform.conversations.application.ports import HandoverDesk
from app.platform.conversations.infrastructure.handover import LoggingHandoverDesk
from app.platform.conversations.infrastructure.sql import SqlConversationsUnitOfWork
from app.platform.conversations.infrastructure.translator import TomlTranslator
from app.platform.conversations.presentation.http.webhooks import build_router
from app.platform.messaging.contracts import InboundMessage, RecordInboundCommand, StatusUpdate
from app.platform.messaging.integration import InboundUseCases, inbound_use_cases
from app.platform.tenancy.contracts import TenancyFacade, TenantRoute
from app.shared.application.conversation import ContactInfo, RouterRule
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.module import ModuleDefinition, PlatformServices

LOCALES = Path(__file__).parent / "locales"


@dataclass(frozen=True)
class ContactsAdapter:
    services: PlatformServices

    async def resolve(
        self, tenant_id: TenantId, wa_id: str, profile_name: str | None
    ) -> ContactInfo:
        resolved = await contacts_for(self.services, tenant_id).resolve(
            ResolveContactCommand(tenant_id, wa_id, profile_name)
        )
        c = resolved.contact
        return ContactInfo(
            id=c.id,
            phone=c.phone,
            profile_name=c.profile_name,
            has_consent=c.has_consent,
            is_opted_out=c.is_opted_out,
            is_new=resolved.is_new,
        )

    async def set_opt_out(self, tenant_id: TenantId, contact_id: UUID, opted_out: bool) -> None:
        actor = Actor.contact(contact_id)
        await contacts_for(self.services, tenant_id).set_opt_out(
            SetOptOutCommand(tenant_id, contact_id, opted_out, actor)
        )

    async def grant_consent(self, tenant_id: TenantId, contact_id: UUID) -> None:
        await contacts_for(self.services, tenant_id).grant_consent(
            GrantConsentCommand(tenant_id, contact_id, Actor.contact(contact_id))
        )


@dataclass(frozen=True)
class InboundLogAdapter:
    services: PlatformServices

    def _for(self, tenant_id: TenantId) -> InboundUseCases:
        s = self.services
        return inbound_use_cases(s.session_factory, tenant_id, s.clock, s.ids)

    async def record(
        self, tenant_id: TenantId, contact_id: UUID, message: InboundMessage
    ) -> UUID | None:
        return await self._for(tenant_id).record_inbound(
            RecordInboundCommand(tenant_id, contact_id, message)
        )

    async def mark_processed(self, tenant_id: TenantId, message_id: UUID) -> None:
        await self._for(tenant_id).mark_processed(message_id)

    async def load(self, tenant_id: TenantId, message_id: UUID) -> tuple[InboundMessage, bool]:
        return await self._for(tenant_id).load(message_id)

    async def record_status(self, tenant_id: TenantId, update: StatusUpdate) -> None:
        await self._for(tenant_id).record_status(update)


@dataclass(frozen=True)
class TenantResolverAdapter:
    tenancy: TenancyFacade

    async def resolve(self, phone_number_id: str) -> TenantRoute | None:
        return await self.tenancy.resolve_phone_number_id(phone_number_id)


@dataclass(frozen=True)
class Conversations:
    webhook_router: APIRouter
    handle_webhook: HandleWebhook
    process_job: ProcessInboundJob
    translator: TomlTranslator


def build_conversations(
    services: PlatformServices,
    modules: Sequence[ModuleDefinition],
    tenancy: TenancyFacade,
    *,
    verify_token: str,
    app_secret: str,
    require_signature: bool,
    handover: HandoverDesk | None = None,
) -> Conversations:
    flows = FlowRegistry()
    rules: list[RouterRule] = []
    locale_dirs: list[Path] = [LOCALES]
    for module in modules:
        for make_flow in module.flows:
            flows.register(make_flow(services))
        rules.extend(make_rule(services) for make_rule in module.router_rules)
        if module.locales_dir is not None:
            locale_dirs.append(module.locales_dir)

    translator = TomlTranslator(_unique(locale_dirs))
    contacts = ContactsAdapter(services)
    inbound = InboundLogAdapter(services)
    tenants = TenantResolverAdapter(tenancy)
    pipeline = HandleInboundMessage(
        lambda tenant_id: SqlConversationsUnitOfWork(services.session_factory, tenant_id),
        FlowEngine(flows),
        Router(rules),
        contacts,
        services.messenger,
        handover or LoggingHandoverDesk(),
        translator,
        services.clock,
        services.ids,
    )
    handle = HandleWebhook(tenants, contacts, inbound, pipeline, services.jobs, services.clock)
    return Conversations(
        webhook_router=build_router(
            handle,
            verify_token=verify_token,
            app_secret=app_secret,
            require_signature=require_signature,
        ),
        handle_webhook=handle,
        process_job=ProcessInboundJob(tenants, contacts, inbound, pipeline),
        translator=translator,
    )


def _unique(paths: Iterable[Path]) -> list[Path]:
    seen: list[Path] = []
    for path in paths:
        if path not in seen:
            seen.append(path)
    return seen
