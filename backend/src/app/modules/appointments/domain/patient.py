"""Patient: a person being treated. One WhatsApp contact can have several (a parent booking for
children - PRD FR-2.3/R4); a patient is stored once and reused for every appointment (DR-1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.appointments.domain.errors import InvalidPatientError
from app.modules.appointments.domain.events import PatientRegistered, PatientUpdated
from app.shared.kernel.actor import Actor
from app.shared.kernel.entity import TenantAggregateRoot
from app.shared.kernel.ids import TenantId


def _valid_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if len(cleaned) < 2 or len(cleaned) > 120:
        raise InvalidPatientError("Please give the patient's full name (2-120 characters)")
    return cleaned


@dataclass(kw_only=True, eq=False)
class Patient(TenantAggregateRoot):
    contact_id: UUID  # the WhatsApp number that books for this patient
    full_name: str
    created_at: datetime

    @classmethod
    def register(
        cls,
        *,
        id: UUID,
        tenant_id: TenantId,
        contact_id: UUID,
        full_name: str,
        actor: Actor,
        at: datetime,
    ) -> Patient:
        patient = cls(
            id=id,
            tenant_id=tenant_id,
            contact_id=contact_id,
            full_name=_valid_name(full_name),
            created_at=at,
        )
        patient.record(
            PatientRegistered(occurred_at=at, patient_id=id, contact_id=contact_id, actor=actor)
        )
        return patient

    def rename(self, full_name: str, *, actor: Actor, at: datetime) -> None:
        name = _valid_name(full_name)
        if name != self.full_name:
            self.full_name = name
            self.record(PatientUpdated(occurred_at=at, patient_id=self.id, actor=actor))
