"""Connect a Meta WhatsApp number to a tenant (super-admin; Embedded Signup later, PRD A1).

The number's access token is NOT stored here; messaging (step 3) keeps credentials encrypted.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.platform.tenancy.application.dto import WhatsAppNumberDTO
from app.platform.tenancy.application.unit_of_work import TenancyUnitOfWork
from app.platform.tenancy.domain.whatsapp_number import WhatsAppNumber
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId


@dataclass(frozen=True)
class ConnectWhatsAppNumberCommand:
    tenant_id: TenantId
    phone_number_id: str
    display_phone: str
    actor: Actor


class ConnectWhatsAppNumber:
    def __init__(self, uow: TenancyUnitOfWork, clock: Clock, ids: IdGenerator) -> None:
        self._uow, self._clock, self._ids = uow, clock, ids

    async def __call__(self, cmd: ConnectWhatsAppNumberCommand) -> WhatsAppNumberDTO:
        async with self._uow as uow:
            await uow.tenants.get(cmd.tenant_id)  # must exist
            number = WhatsAppNumber.connect(
                id=self._ids.new_id(),
                tenant_id=cmd.tenant_id,
                phone_number_id=cmd.phone_number_id,
                display_phone=cmd.display_phone,
                actor=cmd.actor,
                at=self._clock.now(),
            )
            await uow.whatsapp_numbers.add(number)
            await uow.commit()
        return WhatsAppNumberDTO.from_domain(number)
