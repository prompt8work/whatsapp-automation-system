from __future__ import annotations

from collections.abc import Collection
from typing import Protocol
from uuid import UUID

from app.platform.payments.domain.payment import PaymentRequest, PaymentStatus


class PaymentRepository(Protocol):
    """Tenant-scoped (RLS)."""

    async def get(self, payment_id: UUID) -> PaymentRequest:
        """Raises PaymentNotFoundError."""
        ...

    async def by_gateway_ref(self, gateway_ref: str) -> PaymentRequest | None: ...

    async def by_transaction_id(self, transaction_id: str) -> PaymentRequest | None: ...

    async def for_subjects(
        self, subject_type: str, subject_ids: Collection[UUID]
    ) -> list[PaymentRequest]: ...

    async def search(self, status: PaymentStatus | None, limit: int) -> list[PaymentRequest]: ...

    async def add(self, payment: PaymentRequest) -> None: ...

    async def save(self, payment: PaymentRequest) -> None: ...
