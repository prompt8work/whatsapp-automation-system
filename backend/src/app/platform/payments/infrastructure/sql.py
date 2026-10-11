"""SQL repository, Unit of Work (payment events -> append-only history) and settings store."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any, cast
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import CursorResult, RowMapping, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.payments.application.ports import RazorpaySecrets
from app.platform.payments.domain.errors import PaymentNotFoundError, PaymentsNotSetUpError
from app.platform.payments.domain.events import PaymentEvent
from app.platform.payments.domain.payment import (
    PaymentMethod,
    PaymentRequest,
    PaymentSettings,
    PaymentStatus,
)
from app.platform.payments.infrastructure.tables import payment_events, payment_settings, payments
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.infrastructure.serialization import serialize_event
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork
from app.shared.kernel.errors import ConcurrencyConflictError
from app.shared.kernel.events import DomainEvent
from app.shared.kernel.ids import TenantId

_FIELDS = (
    "receipt_number",
    "subject_type",
    "subject_id",
    "contact_id",
    "payer_name",
    "payer_phone",
    "purpose",
    "amount_minor",
    "currency",
    "created_at",
    "expires_at",
    "gateway_ref",
    "pay_url",
    "transaction_id",
    "paid_at",
    "refunded_at",
    "note",
    "version",
)


def _payment(r: RowMapping) -> PaymentRequest:
    return PaymentRequest(
        id=r["id"],
        tenant_id=TenantId(r["tenant_id"]),
        method=PaymentMethod(r["method"]),
        status=PaymentStatus(r["status"]),
        **{f: r[f] for f in _FIELDS},
    )


def _row(p: PaymentRequest) -> dict[str, Any]:
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "method": p.method.value,
        "status": p.status.value,
        **{f: getattr(p, f) for f in _FIELDS},
    }


class SqlPaymentRepository:
    def __init__(self, session: AsyncSession, uow: UnitOfWork) -> None:
        self._session, self._uow = session, uow

    async def _many(self, stmt: Any) -> list[PaymentRequest]:
        found = [_payment(r) for r in (await self._session.execute(stmt)).mappings()]
        for p in found:
            self._uow.track(p)
        return found

    async def get(self, payment_id: UUID) -> PaymentRequest:
        found = await self._many(select(payments).where(payments.c.id == payment_id))
        if not found:
            raise PaymentNotFoundError()
        return found[0]

    async def by_gateway_ref(self, gateway_ref: str) -> PaymentRequest | None:
        found = await self._many(select(payments).where(payments.c.gateway_ref == gateway_ref))
        return found[0] if found else None

    async def by_transaction_id(self, transaction_id: str) -> PaymentRequest | None:
        found = await self._many(
            select(payments).where(payments.c.transaction_id == transaction_id)
        )
        return found[0] if found else None

    async def for_subjects(
        self, subject_type: str, subject_ids: Collection[UUID]
    ) -> list[PaymentRequest]:
        if not subject_ids:
            return []
        return await self._many(
            select(payments).where(
                payments.c.subject_type == subject_type,
                payments.c.subject_id.in_(list(subject_ids)),
            )
        )

    async def search(self, status: PaymentStatus | None, limit: int) -> list[PaymentRequest]:
        stmt = select(payments)
        if status is not None:
            stmt = stmt.where(payments.c.status == status.value)
        return await self._many(stmt.order_by(payments.c.created_at.desc()).limit(limit))

    async def add(self, payment: PaymentRequest) -> None:
        await self._session.execute(insert(payments).values(_row(payment)))
        self._uow.track(payment)

    async def save(self, payment: PaymentRequest) -> None:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(payments)
                .where(payments.c.id == payment.id, payments.c.version == payment.version)
                .values(_row(payment) | {"version": payment.version + 1})
            ),
        )
        if result.rowcount != 1:
            raise ConcurrencyConflictError()
        payment.version += 1
        self._uow.track(payment)


class SqlPaymentsUnitOfWork(SqlUnitOfWork):
    payments: SqlPaymentRepository

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], tenant_id: TenantId
    ) -> None:
        super().__init__(session_factory, tenant_id)
        self._tenant = tenant_id

    def _create_repositories(self) -> None:
        self.payments = SqlPaymentRepository(self.session, self)

    async def _save_events(self, events: list[DomainEvent]) -> None:
        await super()._save_events(events)  # outbox
        rows = [
            {
                "id": e.event_id,
                "tenant_id": self._tenant,
                "payment_id": e.payment_id,
                "event_type": e.event_type,
                "actor": str(getattr(e, "actor", "system")),
                "payload": serialize_event(e),
                "occurred_at": e.occurred_at,
            }
            for e in events
            if isinstance(e, PaymentEvent)
        ]
        if rows:
            await self.session.execute(insert(payment_events), rows)


class SqlPaymentSettingsStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], key: str) -> None:
        self._session_factory = session_factory
        self._fernet = Fernet(key.encode()) if key else None

    async def _row(self, tenant_id: TenantId) -> RowMapping | None:
        async with SqlUnitOfWork(self._session_factory, tenant_id) as uow:
            return (
                (
                    await uow.session.execute(
                        select(payment_settings).where(payment_settings.c.tenant_id == tenant_id)
                    )
                )
                .mappings()
                .one_or_none()
            )

    async def get(self, tenant_id: TenantId) -> PaymentSettings:
        row = await self._row(tenant_id)
        if row is None:
            return PaymentSettings()
        return PaymentSettings(
            methods=tuple(PaymentMethod(m) for m in row["methods"]),
            whatsapp_pay_configuration=row["whatsapp_pay_configuration"],
            razorpay_key_id=row["razorpay_key_id"],
        )

    async def _upsert(self, tenant_id: TenantId, values: dict[str, Any]) -> None:
        defaults = {"methods": [], "whatsapp_pay_configuration": "", "razorpay_key_id": ""}
        async with SqlUnitOfWork(self._session_factory, tenant_id) as uow:
            await uow.session.execute(
                pg_insert(payment_settings)
                .values(tenant_id=tenant_id, **(defaults | values))
                .on_conflict_do_update(
                    index_elements=["tenant_id"], set_=values | {"updated_at": func.now()}
                )
            )
            await uow.commit()

    async def put(self, tenant_id: TenantId, settings: PaymentSettings) -> None:
        await self._upsert(
            tenant_id,
            {
                "methods": [m.value for m in settings.methods],
                "whatsapp_pay_configuration": settings.whatsapp_pay_configuration,
                "razorpay_key_id": settings.razorpay_key_id,
            },
        )

    async def secrets(self, tenant_id: TenantId) -> RazorpaySecrets | None:
        row = await self._row(tenant_id)
        if self._fernet is None or row is None or not row["razorpay_key_secret_encrypted"]:
            return None
        return RazorpaySecrets(
            self._fernet.decrypt(row["razorpay_key_secret_encrypted"].encode()).decode(),
            self._fernet.decrypt(row["razorpay_webhook_secret_encrypted"].encode()).decode(),
        )

    async def put_secrets(self, tenant_id: TenantId, secrets: RazorpaySecrets) -> None:
        if self._fernet is None:
            raise PaymentsNotSetUpError("The server needs CREDENTIALS_KEY to store payment keys")
        fernet = self._fernet
        await self._upsert(
            tenant_id,
            {
                "razorpay_key_secret_encrypted": fernet.encrypt(
                    secrets.key_secret.encode()
                ).decode(),
                "razorpay_webhook_secret_encrypted": fernet.encrypt(
                    secrets.webhook_secret.encode()
                ).decode(),
            },
        )
