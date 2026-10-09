"""Consent and opt-out (PRD PL-2.4). The bot calls these on "Yes" / "STOP"; staff can too."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.platform.contacts.application.dto import ContactDTO
from app.platform.contacts.application.unit_of_work import ContactsUnitOfWork
from app.shared.application.audit import AuditLogger, AuditRecord
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import TenantId


@dataclass(frozen=True)
class GrantConsentCommand:
    tenant_id: TenantId
    contact_id: UUID
    actor: Actor


class GrantConsent:
    def __init__(self, uow: ContactsUnitOfWork, clock: Clock, audit: AuditLogger) -> None:
        self._uow, self._clock, self._audit = uow, clock, audit

    async def __call__(self, cmd: GrantConsentCommand) -> ContactDTO:
        async with self._uow as uow:
            contact = await uow.contacts.get(cmd.contact_id)
            contact.grant_consent(actor=cmd.actor, at=self._clock.now())
            await uow.contacts.save(contact)
            await uow.commit()
        await self._audit.record(
            AuditRecord(cmd.tenant_id, cmd.actor, "contact.consent", "contact", cmd.contact_id)
        )
        return ContactDTO.from_domain(contact)


@dataclass(frozen=True)
class SetOptOutCommand:
    tenant_id: TenantId
    contact_id: UUID
    opted_out: bool
    actor: Actor


class SetOptOut:
    def __init__(self, uow: ContactsUnitOfWork, clock: Clock, audit: AuditLogger) -> None:
        self._uow, self._clock, self._audit = uow, clock, audit

    async def __call__(self, cmd: SetOptOutCommand) -> ContactDTO:
        now = self._clock.now()
        async with self._uow as uow:
            contact = await uow.contacts.get(cmd.contact_id)
            if cmd.opted_out:
                contact.opt_out(actor=cmd.actor, at=now)
            else:
                contact.opt_in(actor=cmd.actor, at=now)
            await uow.contacts.save(contact)
            await uow.commit()
        action = "contact.opt_out" if cmd.opted_out else "contact.opt_in"
        await self._audit.record(
            AuditRecord(cmd.tenant_id, cmd.actor, action, "contact", cmd.contact_id)
        )
        return ContactDTO.from_domain(contact)
