"""Retry policy shared by scheduled jobs and outbox deliveries: 1, 2, 4, 8 … minutes, max 1 h."""

from __future__ import annotations

from datetime import timedelta

MAX_BACKOFF = timedelta(hours=1)


def backoff(attempt: int) -> timedelta:
    return min(timedelta(minutes=2 ** max(0, attempt - 1)), MAX_BACKOFF)


def short_error(error: BaseException) -> str:
    """Error type + message, trimmed. Callers must not put personal data in exception text."""
    return f"{type(error).__name__}: {error}"[:2000]
