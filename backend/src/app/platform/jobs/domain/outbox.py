"""Delivery state of one outbox row (an event waiting for its handlers)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from app.platform.jobs.domain.retry import backoff, short_error
from app.shared.kernel.ids import TenantId

MAX_DELIVERY_ATTEMPTS = 10


@dataclass(kw_only=True, eq=False)
class OutboxDelivery:
    id: UUID  # = event_id
    tenant_id: TenantId | None
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    attempts: int = 0
    next_attempt_at: datetime | None = None
    last_error: str | None = None
    dispatched_at: datetime | None = None
    dead_at: datetime | None = None

    def claim(self, now: datetime, lease: timedelta) -> None:
        """Lease the row so another tick does not deliver it at the same time."""
        self.attempts += 1
        self.next_attempt_at = now + lease

    def delivered(self, now: datetime) -> None:
        self.dispatched_at = now
        self.last_error = None

    def failed(self, error: BaseException, now: datetime) -> None:
        self.last_error = short_error(error)
        if self.attempts >= MAX_DELIVERY_ATTEMPTS:
            self.dead_at = now  # needs a human; visible in logs/metrics
        else:
            self.next_attempt_at = now + backoff(self.attempts)
