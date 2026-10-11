"""Payments wiring. The core (gateways, settings store, facade) is built ONCE by
bootstrap/container.py - modules use it as `services.payments`. Routers and the WhatsApp
payment-result sink are built from that core by bootstrap (they need the container)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import httpx
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.messaging.contracts import PaymentNotice
from app.platform.payments.application.ports import GatewayUpdate, PaymentGateway
from app.platform.payments.application.use_cases import (
    ApplyGatewayUpdate,
    ExpirePayment,
    ListPayments,
    PaymentSettingsUseCases,
    PayMessage,
    RequestPayment,
    StaffPaymentActions,
    SubjectPayments,
)
from app.platform.payments.contracts import PaymentsFacade
from app.platform.payments.domain.payment import PaymentMethod
from app.platform.payments.infrastructure.gateways.at_clinic import AtClinicGateway
from app.platform.payments.infrastructure.gateways.razorpay import (
    API as RAZORPAY_API,
)
from app.platform.payments.infrastructure.gateways.razorpay import (
    RazorpayLinkGateway,
    parse_razorpay_webhook,
    verify_razorpay_signature,
)
from app.platform.payments.infrastructure.gateways.whatsapp_pay import WhatsAppPayGateway
from app.platform.payments.infrastructure.sql import (
    SqlPaymentSettingsStore,
    SqlPaymentsUnitOfWork,
)
from app.platform.payments.presentation.http.routers import (
    PaymentsUseCases,
    build_router,
    build_webhook_router,
)
from app.shared.application.audit import AuditLogger
from app.shared.application.jobs import JobScheduler
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId


@dataclass(frozen=True)
class PaymentsCore:
    session_factory: async_sessionmaker[AsyncSession]
    settings: SqlPaymentSettingsStore
    gateways: Mapping[PaymentMethod, PaymentGateway]
    facade: PaymentsFacade
    jobs: JobScheduler
    audit: AuditLogger
    clock: Clock
    ids: IdGenerator

    def uow(self, tenant_id: TenantId) -> SqlPaymentsUnitOfWork:
        return SqlPaymentsUnitOfWork(self.session_factory, tenant_id)

    def apply(self, tenant_id: TenantId) -> ApplyGatewayUpdate:
        return ApplyGatewayUpdate(self.uow(tenant_id), self.clock)

    def expire_job(self) -> ExpirePayment:
        return ExpirePayment(self.uow, self.clock)


def build_payments_core(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    credentials_key: str,
    http_client: httpx.AsyncClient,
    jobs: JobScheduler,
    audit: AuditLogger,
    clock: Clock,
    ids: IdGenerator,
    razorpay_api: str = RAZORPAY_API,
) -> PaymentsCore:
    settings = SqlPaymentSettingsStore(session_factory, credentials_key)
    gateways: dict[PaymentMethod, PaymentGateway] = {
        g.method: g
        for g in (
            WhatsAppPayGateway(),
            RazorpayLinkGateway(http_client, razorpay_api),
            AtClinicGateway(),
        )
    }

    def uow(tenant_id: TenantId) -> SqlPaymentsUnitOfWork:
        return SqlPaymentsUnitOfWork(session_factory, tenant_id)

    facade = PaymentsFacade(
        request=lambda t: RequestPayment(uow(t), settings, gateways, jobs, clock, ids),
        message=lambda t: PayMessage(uow(t), settings, gateways),
        subjects=lambda t: SubjectPayments(uow(t), clock),
        settings=settings,
    )
    return PaymentsCore(session_factory, settings, gateways, facade, jobs, audit, clock, ids)


def build_payments_routers(core: PaymentsCore) -> tuple[APIRouter, APIRouter]:
    """(dashboard router - mount under /api, Razorpay webhook router - mount at the root)."""

    def for_tenant(tenant_id: TenantId) -> PaymentsUseCases:
        uow = core.uow(tenant_id)
        return PaymentsUseCases(
            list_payments=ListPayments(uow),
            subjects=SubjectPayments(uow, core.clock),
            staff=StaffPaymentActions(uow, core.settings, core.gateways, core.audit, core.clock),
            settings=PaymentSettingsUseCases(core.settings, core.audit),
        )

    async def receive_razorpay(
        tenant_id: TenantId, body: bytes, signature: str | None
    ) -> bool | None:
        secrets = await core.settings.secrets(tenant_id)
        if secrets is None or not verify_razorpay_signature(
            secrets.webhook_secret, body, signature
        ):
            return None
        update = parse_razorpay_webhook(body)
        return bool(update) and await core.apply(tenant_id)(update)  # type: ignore[arg-type]

    return build_router(for_tenant), build_webhook_router(receive_razorpay)


@dataclass(frozen=True)
class WhatsAppPaymentSink:
    """The conversation pipeline's PaymentNoticeSink: WhatsApp Payments results (PL-6.1 A)."""

    core: PaymentsCore

    async def apply(self, tenant_id: TenantId, notice: PaymentNotice) -> None:
        update = {
            "captured": GatewayUpdate("paid", notice.reference_id, notice.transaction_id),
            "failed": GatewayUpdate("failed", notice.reference_id, notice.transaction_id),
        }.get(notice.status)
        if update is not None:  # "pending" etc. - nothing to record yet
            await self.core.apply(tenant_id)(update)
