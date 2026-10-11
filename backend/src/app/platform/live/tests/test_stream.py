from __future__ import annotations

from uuid import uuid4

from app.platform.live.application.stream import LiveStream, LiveUpdate
from app.shared.kernel.ids import TenantId

TENANT = TenantId(uuid4())


async def test_first_answer_has_the_versions_then_only_changes() -> None:
    reads = iter([{"inbox": 1}, {"inbox": 1}, {"inbox": 2, "payments": 1}])

    async def read(_: TenantId) -> dict[str, int]:
        return next(reads)

    async def no_wait(_: float) -> None:
        return None

    stream = LiveStream(read, poll=1, window=3, sleep=no_wait)
    updates = [u async for u in stream(TENANT, {})]
    assert updates == [
        LiveUpdate(("inbox",), {"inbox": 1}),  # a fresh client learns everything once
        LiveUpdate(("inbox", "payments"), {"inbox": 2, "payments": 1}),
    ]


async def test_reconnecting_client_hears_only_what_it_missed() -> None:
    async def read(_: TenantId) -> dict[str, int]:
        return {"inbox": 5, "appointments": 9}

    async def no_wait(_: float) -> None:
        return None

    stream = LiveStream(read, poll=1, window=1, sleep=no_wait)
    [update] = [u async for u in stream(TENANT, {"inbox": 5, "appointments": 8})]
    assert update.changed == ("appointments",)
