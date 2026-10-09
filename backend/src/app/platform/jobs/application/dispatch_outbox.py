"""Deliver stored domain events to their handlers (ARCHITECTURE §8.4).

At-least-once: if one of an event's handlers fails, the whole event is retried later, so
every handler must be idempotent (key on `event.event_id`).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta

from app.platform.jobs.application.registry import EventHandlerRegistry
from app.platform.jobs.application.unit_of_work import JobsUnitOfWork
from app.platform.jobs.domain.outbox import OutboxDelivery
from app.shared.application.events import StoredEvent
from app.shared.kernel.clock import Clock

log = logging.getLogger(__name__)


@dataclass
class DispatchReport:
    delivered: int = 0
    retrying: int = 0
    dead: int = 0


class DispatchOutbox:
    def __init__(
        self,
        uow: JobsUnitOfWork,
        handlers: EventHandlerRegistry,
        clock: Clock,
        *,
        batch_size: int = 50,
        lease: timedelta = timedelta(minutes=2),
        budget: timedelta = timedelta(seconds=10),
    ) -> None:
        self._uow, self._handlers, self._clock = uow, handlers, clock
        self._batch_size, self._lease, self._budget = batch_size, lease, budget

    async def __call__(self) -> DispatchReport:
        report = DispatchReport()
        deadline = time.monotonic() + self._budget.total_seconds()
        while time.monotonic() < deadline:
            batch = await self._claim_batch()
            if not batch:
                break
            for delivery in batch:
                await self._deliver(delivery, report)
        return report

    async def _claim_batch(self) -> list[OutboxDelivery]:
        async with self._uow as uow:
            batch = await uow.outbox.lock_due(self._clock.now(), self._batch_size)
            for delivery in batch:
                delivery.claim(self._clock.now(), self._lease)
                await uow.outbox.save(delivery)
            await uow.commit()
        return batch

    async def _deliver(self, delivery: OutboxDelivery, report: DispatchReport) -> None:
        event = StoredEvent(
            event_id=delivery.id,
            event_type=delivery.event_type,
            tenant_id=delivery.tenant_id,
            occurred_at=delivery.occurred_at,
            payload=delivery.payload,
        )
        try:
            for handler in self._handlers.for_type(delivery.event_type):
                await handler(event)
        except Exception as exc:
            delivery.failed(exc, self._clock.now())
            log.warning(
                "outbox.delivery_failed",
                extra={"event_id": str(delivery.id), "event_type": delivery.event_type},
            )
            if delivery.dead_at:
                report.dead += 1
            else:
                report.retrying += 1
        else:
            delivery.delivered(self._clock.now())
            report.delivered += 1
        async with self._uow as uow:
            await uow.outbox.save(delivery)
            await uow.commit()
