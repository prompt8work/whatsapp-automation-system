"""Retention use cases (PRD §7.10).

RunRetention   the daily job: every tenant x every module's Purger -> purge what is due.
Upcoming       the staff "deleting in the next 7 days" list (AP-10.6).
RecordDeletion writes the deletion record; also used by on-request deletions (AP-10.13).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.platform.retention.application.ports import DeletionRecords, TenantList
from app.platform.retention.domain.record import DeletionRecord
from app.shared.application.jobs import JobContext
from app.shared.application.retention import Purger, PurgeResult, PurgeTarget
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId

log = logging.getLogger(__name__)

RUN_JOB = "retention.run"
UPCOMING_WINDOW = timedelta(days=7)


class RecordDeletion:
    def __init__(self, records: DeletionRecords, clock: Clock, ids: IdGenerator) -> None:
        self._records, self._clock, self._ids = records, clock, ids

    async def __call__(
        self, tenant_id: TenantId, purger: str, target: PurgeTarget, result: PurgeResult
    ) -> None:
        await self._records.add(
            DeletionRecord(
                id=self._ids.new_id(),
                tenant_id=tenant_id,
                purger=purger,
                subject_type=target.subject_type,
                subject_id=target.subject_id,
                rule=target.rule,
                counts={k: v for k, v in result.counts.items() if v},
                at=self._clock.now(),
            )
        )


@dataclass(frozen=True)
class RetentionRun:
    purged: int
    failed: int


class RunRetention:
    """Idempotent: what is gone is no longer due, so a re-run just continues."""

    def __init__(
        self,
        tenants: TenantList,
        purgers: Sequence[Purger],
        record: RecordDeletion,
        clock: Clock,
    ) -> None:
        self._tenants, self._purgers, self._record, self._clock = tenants, purgers, record, clock

    async def __call__(self) -> RetentionRun:
        now, purged, failed = self._clock.now(), 0, 0
        for tenant_id in await self._tenants.all_tenant_ids():
            for purger in self._purgers:  # module order: cases before the contacts they free
                for target in await purger.due(tenant_id, now):
                    try:
                        result = await purger.purge(tenant_id, target)
                    except Exception:
                        failed += 1
                        log.exception(
                            "purge failed",
                            extra={"purger": purger.key, "subject_id": str(target.subject_id)},
                        )
                        continue
                    if result.counts:  # empty = no longer due (reopened, hold, ...)
                        await self._record(tenant_id, purger.key, target, result)
                        purged += 1
        log.info("retention run", extra={"purged": purged, "failed": failed})
        return RetentionRun(purged, failed)

    async def handle(self, ctx: JobContext) -> None:
        """Job handler. Failures are re-tried by the next attempt / tomorrow's run."""
        run = await self()
        if run.failed:
            raise RuntimeError(f"{run.failed} purge(s) failed; see logs")


@dataclass(frozen=True)
class UpcomingDeletion:
    purger: str
    target: PurgeTarget


class Upcoming:
    def __init__(self, purgers: Sequence[Purger], clock: Clock) -> None:
        self._purgers, self._clock = purgers, clock

    async def __call__(self, tenant_id: TenantId) -> list[UpcomingDeletion]:
        until: datetime = self._clock.now() + UPCOMING_WINDOW
        found = [
            UpcomingDeletion(p.key, t) for p in self._purgers for t in await p.due(tenant_id, until)
        ]
        return sorted(found, key=lambda u: u.target.due_at)


class ListDeletionRecords:
    def __init__(self, records: DeletionRecords) -> None:
        self._records = records

    async def __call__(self, tenant_id: TenantId, limit: int = 200) -> list[DeletionRecord]:
        return await self._records.list(tenant_id, limit)
