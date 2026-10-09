"""Time. The domain never calls `datetime.now()`; it receives a `Clock`.

All datetimes inside the system are timezone-aware UTC. Conversion to a location's
timezone happens only at the edges (bot messages, dashboard).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
