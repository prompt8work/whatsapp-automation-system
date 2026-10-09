"""/internal/jobs/tick - called every minute by Vercel Cron (backend/vercel.json).

Vercel Cron sends `Authorization: Bearer $CRON_SECRET`. Not under /api, so the dashboard's
/api rewrite never exposes it. Order: deliver events first (they may schedule jobs), then jobs.
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from app.platform.jobs.application.dispatch_outbox import DispatchOutbox
from app.platform.jobs.application.run_due_jobs import RunDueJobs


class TickResponse(BaseModel):
    events_delivered: int
    events_retrying: int
    events_dead: int
    jobs_succeeded: int
    jobs_retrying: int
    jobs_failed: int


def build_router(dispatch: DispatchOutbox, run_jobs: RunDueJobs, cron_secret: str) -> APIRouter:
    router = APIRouter(prefix="/internal/jobs", tags=["internal"], include_in_schema=False)
    expected = f"Bearer {cron_secret}".encode()

    async def tick(authorization: Annotated[str | None, Header()] = None) -> TickResponse:
        if not hmac.compare_digest((authorization or "").encode(), expected):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad cron secret")
        events = await dispatch()
        jobs = await run_jobs()
        return TickResponse(
            events_delivered=events.delivered,
            events_retrying=events.retrying,
            events_dead=events.dead,
            jobs_succeeded=jobs.succeeded,
            jobs_retrying=jobs.retrying,
            jobs_failed=jobs.failed,
        )

    router.add_api_route("/tick", tick, methods=["GET", "POST"])
    return router
