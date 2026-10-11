from __future__ import annotations

from typing import Protocol

from app.platform.payments.domain.repositories import PaymentRepository
from app.shared.application.unit_of_work import UnitOfWork


class PaymentsUnitOfWork(UnitOfWork, Protocol):
    @property
    def payments(self) -> PaymentRepository: ...
