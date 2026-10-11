"""Settings → WhatsApp templates: which approved template each slot uses (PRD PL-4.2)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.platform.messaging.application.unit_of_work import MessagingUnitOfWork
from app.platform.messaging.domain.templates import TemplateMapping
from app.shared.application.audit import AuditLogger, AuditRecord
from app.shared.application.messaging import TemplateSlot
from app.shared.kernel.actor import Actor
from app.shared.kernel.errors import NotFoundError
from app.shared.kernel.ids import TenantId


class UnknownTemplateSlotError(NotFoundError):
    code = "messaging.unknown_slot"


@dataclass(frozen=True)
class SlotView:
    slot: TemplateSlot
    mapping: TemplateMapping | None


class TemplateSettings:
    def __init__(
        self, uow: MessagingUnitOfWork, slots: Sequence[TemplateSlot], audit: AuditLogger
    ) -> None:
        self._uow, self._audit = uow, audit
        self._slots = {s.key: s for s in slots}

    async def list(self) -> list[SlotView]:
        async with self._uow as uow:
            mapped = {m.slot: m for m in await uow.templates.list()}
        return [SlotView(s, mapped.get(k)) for k, s in self._slots.items()]  # modules' order

    async def set(
        self, tenant_id: TenantId, slot: str, name: str | None, language: str, actor: Actor
    ) -> None:
        """name None (or empty) removes the mapping."""
        if slot not in self._slots:
            raise UnknownTemplateSlotError()
        async with self._uow as uow:
            if name:
                await uow.templates.put(TemplateMapping(slot, name.strip(), language.strip()))
            else:
                await uow.templates.delete(slot)
            await uow.commit()
        await self._audit.record(
            AuditRecord(tenant_id, actor, "template.mapped", "template", None, {"slot": slot})
        )
