"""Delivery receipts (sent / delivered / read / failed) from the webhook, and per-number
credentials (super-admin)."""

from __future__ import annotations

from dataclasses import dataclass

from app.platform.messaging.application.unit_of_work import MessagingUnitOfWork
from app.platform.messaging.domain.inbound import StatusUpdate
from app.platform.messaging.domain.repositories import CredentialStore
from app.shared.kernel.errors import ValidationError


class RecordDeliveryStatus:
    def __init__(self, uow: MessagingUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, update: StatusUpdate) -> bool:
        """False if the message is unknown (e.g. sent from Meta's own tools)."""
        async with self._uow as uow:
            message = await uow.messages.find_by_wa_id(update.wa_message_id)
            if message is None:
                return False
            message.apply_delivery_status(update.status, update.error)
            await uow.messages.save(message)
            await uow.commit()
        return True


@dataclass(frozen=True)
class SetCredentialsCommand:
    phone_number_id: str
    access_token: str


class SetCredentials:
    def __init__(self, store: CredentialStore) -> None:
        self._store = store

    async def __call__(self, cmd: SetCredentialsCommand) -> None:
        if len(cmd.access_token.strip()) < 20:
            raise ValidationError("That does not look like a Meta access token")
        await self._store.put(cmd.phone_number_id, cmd.access_token.strip())
