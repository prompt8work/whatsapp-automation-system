"""GET /api/live - Server-Sent Events: which dashboard topics changed (§8.9).

    event: change
    data: {"changed": ["appointments"], "versions": {"appointments": 7, "inbox": 3}}

The stream ends after ~25 s; the client reconnects with ?since=<versions JSON>. The dashboard
reads it with fetch() (so it can send the Authorization header), not EventSource.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.platform.live.application.stream import LiveStream
from app.shared.presentation.request_context import RequestContext, get_request_context

Member = Annotated[RequestContext, Depends(get_request_context)]


def build_router(stream: LiveStream) -> APIRouter:
    router = APIRouter(prefix="/live", tags=["live"])

    @router.get("", response_class=StreamingResponse)
    async def live(
        ctx: Member, since: Annotated[str, Query(max_length=2000)] = "{}"
    ) -> StreamingResponse:
        try:
            seen = {str(k): int(v) for k, v in json.loads(since).items()}
        except (ValueError, AttributeError):
            seen = {}

        async def events() -> AsyncIterator[str]:
            yield "retry: 1000\n\n"  # reconnect quickly when the window ends
            async for update in stream(ctx.tenant_id, seen):
                body = json.dumps({"changed": list(update.changed), "versions": update.versions})
                yield f"event: change\ndata: {body}\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
