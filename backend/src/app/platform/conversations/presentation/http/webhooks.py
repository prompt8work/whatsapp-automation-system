"""/webhooks/whatsapp - Meta calls this (not under /api; not for browsers).

GET  : subscription check - echo hub.challenge when hub.verify_token matches.
POST : events - verify X-Hub-Signature-256, parse, process. Always answers 200 once the
       messages are stored, otherwise Meta retries the same delivery for hours.
"""

from __future__ import annotations

import hmac
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.platform.conversations.application.handle_webhook import WebhookReport
from app.platform.messaging.contracts import WebhookBatch
from app.platform.messaging.integration import parse_webhook, verify_signature

log = logging.getLogger(__name__)


def build_router(
    handle: Callable[[WebhookBatch], Awaitable[WebhookReport]],
    *,
    verify_token: str,
    app_secret: str,
    require_signature: bool,
) -> APIRouter:
    router = APIRouter(prefix="/webhooks/whatsapp", tags=["webhooks"], include_in_schema=False)

    @router.get("", response_class=PlainTextResponse)
    async def subscribe(
        mode: Annotated[str, Query(alias="hub.mode")] = "",
        token: Annotated[str, Query(alias="hub.verify_token")] = "",
        challenge: Annotated[str, Query(alias="hub.challenge")] = "",
    ) -> str:
        if mode != "subscribe" or not hmac.compare_digest(token.encode(), verify_token.encode()):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Verification failed")
        return challenge

    @router.post("")
    async def receive(
        request: Request,
        signature: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
    ) -> dict[str, int]:
        body = await request.body()
        if app_secret:
            if not verify_signature(app_secret, body, signature):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad signature")
        elif require_signature:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Webhook secret not configured"
            )
        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON") from exc
        report = await handle(parse_webhook(payload))
        if report.failed:
            log.warning("webhook.partial_failure", extra={"failed": report.failed})
        return vars(report)

    return router
