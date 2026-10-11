"""Understanding free text (PRD Phase 2 "LLM intent and date parsing").

The bot's buttons and rule-based parsing come first; this port is asked ONLY when they fail,
e.g. "day after tomorrow evening", "next Tue", "I need to move my visit". Implementations
must never raise: anything unclear, slow or broken is simply None ("didn't understand"),
and the bot asks again as it always did.

Privacy: only the person's message text is passed - never names, phone numbers or ids.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, time
from typing import Protocol


class Understanding(Protocol):
    async def date(self, text: str, today: date) -> date | None:
        """The ONE calendar day the message names (relative to `today`, the clinic's date)."""
        ...

    async def time(self, text: str) -> time | None:
        """The time of day the message names, e.g. "quarter past 5 in the evening" -> 17:15."""
        ...

    async def choose(self, text: str, options: Mapping[str, str]) -> str | None:
        """Which option (key -> label) the message asks for, e.g. "move my visit" -> reschedule."""
        ...


class NoUnderstanding:
    """Default: no AI. The rule-based parsing is all there is."""

    async def date(self, text: str, today: date) -> date | None:
        return None

    async def time(self, text: str) -> time | None:
        return None

    async def choose(self, text: str, options: Mapping[str, str]) -> str | None:
        return None
