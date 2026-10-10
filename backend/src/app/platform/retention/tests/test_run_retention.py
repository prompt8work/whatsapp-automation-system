from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.platform.retention.application.use_cases import (
    RecordDeletion,
    RetentionRun,
    RunRetention,
    Upcoming,
)
from app.platform.retention.domain.record import DeletionRecord
from app.shared.application.retention import PurgeResult, PurgeTarget
from app.shared.kernel.ids import TenantId
from app.shared.testing.fakes import FixedClock, SequentialIds

T1, T2 = TenantId(uuid4()), TenantId(uuid4())


class Tenants:
    async def all_tenant_ids(self) -> list[TenantId]:
        return [T1, T2]


class Records:
    def __init__(self) -> None:
        self.added: list[DeletionRecord] = []

    async def add(self, record: DeletionRecord) -> None:
        self.added.append(record)

    async def list(self, tenant_id: TenantId, limit: int) -> list[DeletionRecord]:
        return [r for r in self.added if r.tenant_id == tenant_id][:limit]


class FakePurger:
    key = "demo.things"

    def __init__(self, due_in_days: dict[UUID, int], *, broken: UUID | None = None) -> None:
        self.due_in_days, self.broken, self.clock = due_in_days, broken, FixedClock()
        self.purged: list[tuple[TenantId, UUID]] = []

    async def due(self, tenant_id: TenantId, until: datetime) -> list[PurgeTarget]:
        now = self.clock.now()
        return [
            PurgeTarget("thing", tid, "RT-1", now + timedelta(days=d), label="Rahul")
            for tid, d in self.due_in_days.items()
            if now + timedelta(days=d) <= until and tenant_id == T1
        ]

    async def purge(self, tenant_id: TenantId, target: PurgeTarget) -> PurgeResult:
        if target.subject_id == self.broken:
            raise RuntimeError("boom")
        self.purged.append((tenant_id, target.subject_id))
        return PurgeResult({"things": 1, "empty": 0})


def run(purger: FakePurger, records: Records) -> RunRetention:
    clock = FixedClock()
    return RunRetention(Tenants(), [purger], RecordDeletion(records, clock, SequentialIds()), clock)


async def test_due_targets_are_purged_and_recorded_without_personal_data() -> None:
    a, b = uuid4(), uuid4()
    purger, records = FakePurger({a: 0, b: 3}), Records()
    assert await run(purger, records)() == RetentionRun(purged=1, failed=0)
    assert purger.purged == [(T1, a)]
    [record] = records.added
    assert (record.subject_id, record.rule, record.counts) == (a, "RT-1", {"things": 1})
    assert "Rahul" not in repr(record)  # the label is for the staff list only


async def test_one_failing_purge_does_not_stop_the_others_but_fails_the_job() -> None:
    a, b = uuid4(), uuid4()
    purger, records = FakePurger({a: 0, b: 0}, broken=a), Records()
    job = run(purger, records)
    assert await job() == RetentionRun(purged=1, failed=1)
    with pytest.raises(RuntimeError, match=r"1 purge\(s\) failed"):  # -> the job is retried
        await job.handle(None)  # type: ignore[arg-type]


async def test_upcoming_lists_the_next_seven_days_soonest_first() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    upcoming = await Upcoming([FakePurger({a: 6, b: 2, c: 8})], FixedClock())(T1)
    assert [u.target.subject_id for u in upcoming] == [b, a]
