"""/payments (dashboard, under /api) and /webhooks/razorpay/{tenant_id} (Razorpay)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.platform.payments.application.ports import RazorpaySecrets
from app.platform.payments.application.use_cases import (
    ListPayments,
    PaymentSettingsUseCases,
    StaffPaymentActions,
    StaffPaymentCommand,
    SubjectPayments,
)
from app.platform.payments.domain.payment import PaymentMethod, PaymentSettings, PaymentStatus
from app.platform.payments.presentation.http.schemas import (
    NoteRequest,
    PaymentResponse,
    PaymentSettingsResponse,
    PaymentSettingsSchema,
    RazorpaySecretsRequest,
)
from app.shared.kernel.ids import TenantId
from app.shared.presentation.request_context import RequestContext, require

HTTP_ERROR_STATUS = {
    "payments.not_found": status.HTTP_404_NOT_FOUND,
    "payments.invalid_transition": status.HTTP_409_CONFLICT,
    "payments.not_set_up": status.HTTP_409_CONFLICT,
    "payments.gateway_error": status.HTTP_502_BAD_GATEWAY,
    "payments.refund_not_supported": status.HTTP_409_CONFLICT,
}

CanRead = Annotated[RequestContext, Depends(require("payment.read"))]
CanMark = Annotated[RequestContext, Depends(require("payment.mark"))]
CanConfigure = Annotated[RequestContext, Depends(require("payment.settings.manage"))]


@dataclass(frozen=True)
class PaymentsUseCases:
    list_payments: ListPayments
    subjects: SubjectPayments
    staff: StaffPaymentActions
    settings: PaymentSettingsUseCases


def webhook_path(tenant_id: UUID) -> str:
    return f"/webhooks/razorpay/{tenant_id}"


def build_router(for_tenant: Callable[[TenantId], PaymentsUseCases]) -> APIRouter:
    router = APIRouter(prefix="/payments", tags=["payments"])

    @router.get("")
    async def list_payments(
        ctx: CanRead,
        status: PaymentStatus | None = None,
        subject_id: Annotated[list[UUID] | None, Query()] = None,
        subject_type: str = "appointment",
    ) -> list[PaymentResponse]:
        uc = for_tenant(ctx.tenant_id)
        found = (
            await uc.subjects.list(subject_type, subject_id)
            if subject_id
            else await uc.list_payments(status)
        )
        return [PaymentResponse.from_dto(p) for p in found]

    # static paths before /{payment_id}
    @router.get("/settings")
    async def get_settings(ctx: CanConfigure) -> PaymentSettingsResponse:
        settings, saved = await for_tenant(ctx.tenant_id).settings.get(ctx.tenant_id)
        return PaymentSettingsResponse(
            methods=[m.value for m in settings.methods],
            whatsapp_pay_configuration=settings.whatsapp_pay_configuration,
            razorpay_key_id=settings.razorpay_key_id,
            razorpay_secrets_saved=saved,
            razorpay_webhook_path=webhook_path(ctx.tenant_id),
        )

    @router.put("/settings", status_code=status.HTTP_204_NO_CONTENT)
    async def put_settings(body: PaymentSettingsSchema, ctx: CanConfigure) -> None:
        settings = PaymentSettings(
            methods=tuple(PaymentMethod(m) for m in dict.fromkeys(body.methods)),
            whatsapp_pay_configuration=body.whatsapp_pay_configuration.strip(),
            razorpay_key_id=body.razorpay_key_id.strip(),
        )
        await for_tenant(ctx.tenant_id).settings.put(ctx.tenant_id, settings, ctx.actor)

    @router.put("/settings/razorpay-secrets", status_code=status.HTTP_204_NO_CONTENT)
    async def put_secrets(body: RazorpaySecretsRequest, ctx: CanConfigure) -> None:
        await for_tenant(ctx.tenant_id).settings.put_secrets(
            ctx.tenant_id, RazorpaySecrets(body.key_secret, body.webhook_secret), ctx.actor
        )

    def staff_route(path: str, action: str) -> None:
        async def handler(payment_id: UUID, body: NoteRequest, ctx: CanMark) -> PaymentResponse:
            staff = for_tenant(ctx.tenant_id).staff
            command = StaffPaymentCommand(ctx.tenant_id, payment_id, ctx.actor, body.note)
            return PaymentResponse.from_dto(await getattr(staff, action)(command))

        handler.__name__ = f"payment_{action}"
        router.add_api_route(path, handler, methods=["POST"])

    staff_route("/{payment_id}/mark-paid", "mark_paid")
    staff_route("/{payment_id}/mark-refunded", "mark_refunded")
    staff_route("/{payment_id}/cancel", "cancel")
    staff_route("/{payment_id}/refund", "refund")
    return router


# (tenant, raw body, signature header) -> None if the signature is wrong, else "changed?"
RazorpayReceiver = Callable[[TenantId, bytes, str | None], Awaitable[bool | None]]


def build_webhook_router(receive: RazorpayReceiver) -> APIRouter:
    """Razorpay calls this directly - not under /api, no login; the signature is the auth."""
    router = APIRouter(tags=["webhooks"], include_in_schema=False)

    @router.post("/webhooks/razorpay/{tenant_id}")
    async def razorpay(
        tenant_id: UUID,
        request: Request,
        x_razorpay_signature: Annotated[str | None, Header()] = None,
    ) -> dict[str, bool]:
        changed = await receive(TenantId(tenant_id), await request.body(), x_razorpay_signature)
        if changed is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad signature")
        return {"changed": changed}

    return router
