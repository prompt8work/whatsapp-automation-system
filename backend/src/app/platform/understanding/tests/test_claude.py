from __future__ import annotations

import json
from datetime import date, time
from typing import Any

import httpx

from app.platform.understanding.infrastructure.claude import ClaudeUnderstanding

TODAY = date(2026, 10, 11)  # a Sunday


def claude(reply: str | None, *, status: int = 200) -> tuple[ClaudeUnderstanding, list[Any]]:
    seen: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((dict(request.headers), json.loads(request.content)))
        return httpx.Response(status, json={"content": [{"type": "text", "text": reply or ""}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ClaudeUnderstanding(client, "sk-test", "claude-haiku-5-5"), seen


async def test_date_is_asked_with_today_and_the_message_as_data() -> None:
    understanding, seen = claude('{"date": "2026-10-13"}')
    assert await understanding.date("day after tomorrow, evening", TODAY) == date(2026, 10, 13)
    headers, body = seen[0]
    assert headers["x-api-key"] == "sk-test"
    assert body["model"] == "claude-haiku-5-5"
    assert body["temperature"] == 0
    assert "Sunday, 2026-10-11" in body["system"]
    assert body["messages"] == [
        {"role": "user", "content": "<message>day after tomorrow, evening</message>"}
    ]


async def test_past_dates_nonsense_and_errors_mean_not_understood() -> None:
    assert await claude('{"date": "2026-10-01"}')[0].date("1st Oct", TODAY) is None
    assert await claude('{"date": null}')[0].date("whenever", TODAY) is None
    assert await claude("Sure! Tuesday works")[0].date("tue", TODAY) is None
    assert await claude(None, status=529)[0].date("tue", TODAY) is None


async def test_time_and_choice_are_validated() -> None:
    assert await claude('Here: {"time": "17:15"}')[0].time("quarter past 5 pm") == time(17, 15)
    assert await claude('{"time": "25:99"}')[0].time("late") is None
    options = {"reschedule": "Reschedule", "cancel": "Cancel"}
    assert (
        await claude('{"option": "reschedule"}')[0].choose("move my visit", options) == "reschedule"
    )
    assert await claude('{"option": "delete_everything"}')[0].choose("x", options) is None


async def test_empty_text_is_never_sent() -> None:
    understanding, seen = claude('{"date": "2026-10-13"}')
    assert await understanding.date("   ", TODAY) is None
    assert seen == []
