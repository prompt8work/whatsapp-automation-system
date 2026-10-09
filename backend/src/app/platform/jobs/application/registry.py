"""Where modules' job and event handlers are registered (filled by bootstrap at startup)."""

from __future__ import annotations

from collections import defaultdict

from app.shared.application.events import EventHandler
from app.shared.application.jobs import JobHandler


class JobHandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler) -> None:
        if job_type in self._handlers:
            raise ValueError(f"Job type {job_type!r} registered twice")
        self._handlers[job_type] = handler

    def get(self, job_type: str) -> JobHandler | None:
        return self._handlers.get(job_type)


class EventHandlerRegistry:
    def __init__(self) -> None:
        self._handlers: defaultdict[str, list[EventHandler]] = defaultdict(list)

    def register(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def for_type(self, event_type: str) -> list[EventHandler]:
        return list(self._handlers.get(event_type, ()))
