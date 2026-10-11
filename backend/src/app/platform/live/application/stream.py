"""Live dashboard updates (ARCHITECTURE §8.9) - framework-free core of /api/live.

Vercel functions can't hold WebSockets, and pooled database connections can't LISTEN. So:
every commit bumps a per-tenant topic counter (live_changes); this loop reads those few rows
every POLL seconds (a primary-key lookup) and yields the topics whose version moved. After
WINDOW seconds it ends; the browser reconnects at once with the versions it has seen, so no
change is missed across reconnects.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass

from app.shared.kernel.ids import TenantId

POLL_SECONDS = 1.5
WINDOW_SECONDS = 25.0

Versions = Mapping[str, int]
ReadVersions = Callable[[TenantId], Awaitable[dict[str, int]]]


@dataclass(frozen=True)
class LiveUpdate:
    changed: tuple[str, ...]  # topics that moved since the client's last versions
    versions: dict[str, int]  # the client sends these back when it reconnects


class LiveStream:
    def __init__(
        self,
        read: ReadVersions,
        *,
        poll: float = POLL_SECONDS,
        window: float = WINDOW_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._read, self._poll, self._window, self._sleep = read, poll, window, sleep

    async def __call__(self, tenant_id: TenantId, seen: Versions) -> AsyncIterator[LiveUpdate]:
        known = dict(seen)
        waited = 0.0
        first = True
        while waited < self._window:
            current = await self._read(tenant_id)
            changed = tuple(sorted(t for t, v in current.items() if known.get(t) != v))
            if changed or first:  # always answer once, so a fresh client learns the versions
                yield LiveUpdate(changed, current)
                known, first = dict(current), False
            await self._sleep(self._poll)
            waited += self._poll
