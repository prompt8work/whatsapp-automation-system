"""/platform/whatsapp-numbers/{phone_number_id}/credentials - super-admin stores the number's
Meta access token. Write-only: the token is never returned by any endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.platform.messaging.application.commands.statuses import (
    SetCredentials,
    SetCredentialsCommand,
)
from app.shared.application.auth import Principal
from app.shared.presentation.request_context import require_super_admin

HTTP_ERROR_STATUS = {
    "messaging.invalid_message": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "messaging.outside_window": status.HTTP_409_CONFLICT,
    "messaging.no_credentials": status.HTTP_409_CONFLICT,
}


class CredentialsRequest(BaseModel):
    access_token: str = Field(min_length=20, max_length=1000)


def build_router(set_credentials: SetCredentials) -> APIRouter:
    router = APIRouter(prefix="/platform/whatsapp-numbers", tags=["platform"])

    @router.put("/{phone_number_id}/credentials", status_code=status.HTTP_204_NO_CONTENT)
    async def put_credentials(
        phone_number_id: str,
        body: CredentialsRequest,
        _: Annotated[Principal, Depends(require_super_admin)],
    ) -> None:
        await set_credentials(SetCredentialsCommand(phone_number_id, body.access_token))

    return router
