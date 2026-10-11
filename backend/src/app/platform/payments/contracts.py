"""Payments' implementation of the shared `Payments` port (app/shared/application/payments.py),
built once by bootstrap/container.py and handed to modules as `services.payments`."""

from __future__ import annotations

from collections.abc import Callable, Collection
from uuid import UUID

from app.platform.payments.application.dto import PaymentDTO
from app.platform.payments.application.ports import PaymentSettingsStore
from app.platform.payments.application.use_cases import (
    PayMessage,
    RequestPayment,
    RequestPaymentCommand,
    SubjectPayments,
)
from app.shared.application.payments import PaymentAsk, PaymentInfo
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import OutboundMessage


def _info(p: PaymentDTO) -> PaymentInfo:
    return PaymentInfo(
        p.id,
        p.receipt_number,
        p.subject_id,
        p.amount_minor,
        p.currency,
        p.method,
        p.status,
        p.pay_url,
        p.paid_at,
    )


class PaymentsFacade:
    def __init__(
        self,
        request: Callable[[TenantId], RequestPayment],
        message: Callable[[TenantId], PayMessage],
        subjects: Callable[[TenantId], SubjectPayments],
        settings: PaymentSettingsStore,
    ) -> None:
        self._request, self._message, self._subjects = request, message, subjects
        self._settings = settings

    async def primary_method(self, tenant_id: TenantId) -> str | None:
        method = (await self._settings.get(tenant_id)).primary_method
        return method.value if method else None

    async def request(self, ask: PaymentAsk) -> PaymentInfo:
        cmd = RequestPaymentCommand(
            ask.tenant_id,
            ask.subject_type,
            ask.subject_id,
            ask.contact_id,
            ask.payer_name,
            ask.payer_phone,
            ask.purpose,
            ask.amount_minor,
            ask.expires_at,
        )
        return _info(await self._request(ask.tenant_id)(cmd))

    async def pay_message(
        self, tenant_id: TenantId, payment_id: UUID, body: str, button: str
    ) -> OutboundMessage | None:
        return await self._message(tenant_id)(tenant_id, payment_id, body, button)

    async def for_subjects(
        self, tenant_id: TenantId, subject_type: str, subject_ids: Collection[UUID]
    ) -> list[PaymentInfo]:
        return [_info(p) for p in await self._subjects(tenant_id).list(subject_type, subject_ids)]

    async def unsettled(
        self, tenant_id: TenantId, subject_type: str, subject_ids: Collection[UUID]
    ) -> set[UUID]:
        return await self._subjects(tenant_id).unsettled(subject_type, subject_ids)

    async def expire(
        self, tenant_id: TenantId, subject_type: str, subject_ids: Collection[UUID], actor: Actor
    ) -> int:
        return await self._subjects(tenant_id).expire(subject_type, subject_ids, actor)

    async def detach(
        self, tenant_id: TenantId, subject_type: str, subject_ids: Collection[UUID]
    ) -> int:
        return await self._subjects(tenant_id).detach(subject_type, subject_ids)
