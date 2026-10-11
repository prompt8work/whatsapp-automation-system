"""Payment use cases (PRD §6.6). Status changes come ONLY from a verified provider update or a
staff action with `payment.mark` - never from what a patient says (PL-6.4)."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.platform.payments.application.dto import PaymentDTO
from app.platform.payments.application.ports import (
    GatewayUpdate,
    PaymentGateway,
    PaymentSettingsStore,
    RazorpaySecrets,
)
from app.platform.payments.application.unit_of_work import PaymentsUnitOfWork
from app.platform.payments.domain.errors import PaymentsNotSetUpError
from app.platform.payments.domain.payment import (
    PaymentMethod,
    PaymentRequest,
    PaymentSettings,
    PaymentStatus,
)
from app.shared.application.audit import AuditLogger, AuditRecord
from app.shared.application.jobs import JobContext, JobScheduler, ScheduleJob
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId
from app.shared.kernel.messages import OutboundMessage

EXPIRE_JOB = "payments.expire"
Gateways = Mapping[PaymentMethod, PaymentGateway]
UowFor = Callable[[TenantId], PaymentsUnitOfWork]


@dataclass(frozen=True)
class RequestPaymentCommand:
    tenant_id: TenantId
    subject_type: str
    subject_id: UUID
    contact_id: UUID | None
    payer_name: str
    payer_phone: str
    purpose: str
    amount_minor: int
    expires_at: datetime | None = None


class RequestPayment:
    """One live payment per subject: asking again returns the existing one (idempotent)."""

    def __init__(
        self,
        uow: PaymentsUnitOfWork,
        settings: PaymentSettingsStore,
        gateways: Gateways,
        jobs: JobScheduler,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._uow, self._settings, self._gateways = uow, settings, gateways
        self._jobs, self._clock, self._ids = jobs, clock, ids

    async def __call__(self, cmd: RequestPaymentCommand) -> PaymentDTO:
        async with self._uow as uow:
            for existing in await uow.payments.for_subjects(cmd.subject_type, [cmd.subject_id]):
                if existing.status in (PaymentStatus.PENDING, PaymentStatus.PAID):
                    return PaymentDTO.from_domain(existing)

        settings = await self._settings.get(cmd.tenant_id)
        method = settings.primary_method
        if method is None:
            raise PaymentsNotSetUpError("Switch on at least one payment method in Settings")
        payment = PaymentRequest.create(
            id=self._ids.new_id(),
            tenant_id=cmd.tenant_id,
            subject_type=cmd.subject_type,
            subject_id=cmd.subject_id,
            contact_id=cmd.contact_id,
            payer_name=cmd.payer_name,
            payer_phone=cmd.payer_phone,
            purpose=cmd.purpose,
            amount_minor=cmd.amount_minor,
            currency=settings.currency,
            method=method,
            expires_at=cmd.expires_at,
            at=self._clock.now(),
        )
        # The provider call happens BEFORE saving: if it fails, nothing half-made is left.
        result = await self._gateways[method].create(
            payment, settings, await self._settings.secrets(cmd.tenant_id)
        )
        payment.attach_gateway(result.gateway_ref, result.pay_url)
        async with self._uow as uow:
            await uow.payments.add(payment)
            await uow.commit()
        if payment.expires_at is not None:
            await self._jobs.schedule(
                ScheduleJob(
                    EXPIRE_JOB,
                    payment.expires_at,
                    f"{EXPIRE_JOB}:{payment.id}",
                    tenant_id=cmd.tenant_id,
                    payload={"payment_id": str(payment.id)},
                )
            )
        return PaymentDTO.from_domain(payment)


class PayMessage:
    """The message the patient taps to pay (resent from the menu or a reminder - R6)."""

    def __init__(
        self, uow: PaymentsUnitOfWork, settings: PaymentSettingsStore, gateways: Gateways
    ) -> None:
        self._uow, self._settings, self._gateways = uow, settings, gateways

    async def __call__(
        self, tenant_id: TenantId, payment_id: UUID, body: str, button: str
    ) -> OutboundMessage | None:
        async with self._uow as uow:
            payment = await uow.payments.get(payment_id)
        if payment.status is not PaymentStatus.PENDING:
            return None
        settings = await self._settings.get(tenant_id)
        return self._gateways[payment.method].message(payment, settings, body, button)


class ApplyGatewayUpdate:
    """A verified webhook (WhatsApp or Razorpay). Idempotent: repeats change nothing."""

    def __init__(self, uow: PaymentsUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, update: GatewayUpdate) -> bool:
        async with self._uow as uow:
            payment = None
            if update.gateway_ref:
                payment = await uow.payments.by_gateway_ref(update.gateway_ref)
            if payment is None and update.transaction_id:
                payment = await uow.payments.by_transaction_id(update.transaction_id)
            if payment is None:
                return False
            now, system = self._clock.now(), Actor.system()
            match update.kind:
                case "paid":
                    changed = payment.mark_paid(
                        actor=system, at=now, transaction_id=update.transaction_id
                    )
                case "failed":
                    changed = payment.mark_failed(at=now)
                case "expired":
                    changed = payment.expire(actor=system, at=now)
                case "refunded":
                    changed = payment.status is PaymentStatus.PAID and payment.mark_refunded(
                        actor=system, at=now
                    )
            if changed:
                await uow.payments.save(payment)
                await uow.commit()
            return changed


@dataclass(frozen=True)
class StaffPaymentCommand:
    tenant_id: TenantId
    payment_id: UUID
    actor: Actor
    note: str = ""


class StaffPaymentActions:
    """Mark as paid / Mark as refunded / Cancel request / Refund via Razorpay (PL-6.4, 6.5).
    Every action is audited."""

    def __init__(
        self,
        uow: PaymentsUnitOfWork,
        settings: PaymentSettingsStore,
        gateways: Gateways,
        audit: AuditLogger,
        clock: Clock,
    ) -> None:
        self._uow, self._settings, self._gateways = uow, settings, gateways
        self._audit, self._clock = audit, clock

    async def _apply(self, cmd: StaffPaymentCommand, action: str) -> PaymentDTO:
        async with self._uow as uow:
            payment = await uow.payments.get(cmd.payment_id)
            now = self._clock.now()
            if action == "mark_paid":
                payment.mark_paid(actor=cmd.actor, at=now, note=cmd.note)
            elif action == "mark_refunded":
                payment.mark_refunded(actor=cmd.actor, at=now, note=cmd.note)
            elif action == "cancel":
                payment.expire(actor=cmd.actor, at=now)
            await uow.payments.save(payment)
            await uow.commit()
        await self._audit.record(
            AuditRecord(cmd.tenant_id, cmd.actor, f"payment.{action}", "payment", payment.id, {})
        )
        return PaymentDTO.from_domain(payment)

    async def mark_paid(self, cmd: StaffPaymentCommand) -> PaymentDTO:
        return await self._apply(cmd, "mark_paid")

    async def mark_refunded(self, cmd: StaffPaymentCommand) -> PaymentDTO:
        return await self._apply(cmd, "mark_refunded")

    async def cancel(self, cmd: StaffPaymentCommand) -> PaymentDTO:
        return await self._apply(cmd, "cancel")

    async def refund(self, cmd: StaffPaymentCommand) -> PaymentDTO:
        """Through the provider (Razorpay links). Others raise RefundNotSupportedError."""
        async with self._uow as uow:
            payment = await uow.payments.get(cmd.payment_id)
        if payment.status is not PaymentStatus.PAID:
            return await self._apply(cmd, "mark_refunded")  # raises the right domain error
        await self._gateways[payment.method].refund(
            payment,
            await self._settings.get(cmd.tenant_id),
            await self._settings.secrets(cmd.tenant_id),
        )
        return await self._apply(cmd, "mark_refunded")


class ExpirePayment:
    """Job handler: an unpaid request whose time ran out."""

    def __init__(self, uow_for: UowFor, clock: Clock) -> None:
        self._uow_for, self._clock = uow_for, clock

    async def __call__(self, ctx: JobContext) -> None:
        assert ctx.tenant_id is not None
        async with self._uow_for(ctx.tenant_id) as uow:
            payment = await uow.payments.get(UUID(ctx.payload["payment_id"]))
            if payment.expire(actor=Actor.system(), at=self._clock.now()):
                await uow.payments.save(payment)
                await uow.commit()


class SubjectPayments:
    """What other modules ask about the payments of their records."""

    def __init__(self, uow: PaymentsUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def list(self, subject_type: str, subject_ids: Collection[UUID]) -> list[PaymentDTO]:
        async with self._uow as uow:
            found = await uow.payments.for_subjects(subject_type, subject_ids)
        return [PaymentDTO.from_domain(p) for p in sorted(found, key=lambda p: p.created_at)]

    async def unsettled(self, subject_type: str, subject_ids: Collection[UUID]) -> set[UUID]:
        """Subjects with a PENDING payment - those block the retention purge (RT-6)."""
        return {
            p.subject_id
            for p in await self.list(subject_type, subject_ids)
            if p.status == PaymentStatus.PENDING.value and p.subject_id is not None
        }

    async def expire(self, subject_type: str, subject_ids: Collection[UUID], actor: Actor) -> int:
        """The record ended unpaid (cancelled, declined, no-show ...): nothing is due (PL-6.5)."""
        async with self._uow as uow:
            changed = 0
            for payment in await uow.payments.for_subjects(subject_type, subject_ids):
                if payment.expire(actor=actor, at=self._clock.now()):
                    await uow.payments.save(payment)
                    changed += 1
            await uow.commit()
        return changed

    async def detach(self, subject_type: str, subject_ids: Collection[UUID]) -> int:
        """RT-7: the records were deleted; the payments stay as ledger entries."""
        async with self._uow as uow:
            found = await uow.payments.for_subjects(subject_type, subject_ids)
            for payment in found:
                payment.detach()
                await uow.payments.save(payment)
            await uow.commit()
        return len(found)


class ListPayments:
    def __init__(self, uow: PaymentsUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, status: PaymentStatus | None, limit: int = 200) -> list[PaymentDTO]:
        async with self._uow as uow:
            return [PaymentDTO.from_domain(p) for p in await uow.payments.search(status, limit)]


class PaymentSettingsUseCases:
    def __init__(self, store: PaymentSettingsStore, audit: AuditLogger) -> None:
        self._store, self._audit = store, audit

    async def get(self, tenant_id: TenantId) -> tuple[PaymentSettings, bool]:
        """(settings, Razorpay secrets saved?) - the secrets themselves never leave."""
        return await self._store.get(tenant_id), await self._store.secrets(tenant_id) is not None

    async def put(self, tenant_id: TenantId, settings: PaymentSettings, actor: Actor) -> None:
        await self._store.put(tenant_id, settings)
        await self._audit.record(
            AuditRecord(tenant_id, actor, "payment.settings_changed", "tenant", tenant_id, {})
        )

    async def put_secrets(
        self, tenant_id: TenantId, secrets: RazorpaySecrets, actor: Actor
    ) -> None:
        await self._store.put_secrets(tenant_id, secrets)
        await self._audit.record(
            AuditRecord(tenant_id, actor, "payment.secrets_changed", "tenant", tenant_id, {})
        )
