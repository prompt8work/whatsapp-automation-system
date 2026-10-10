"""Appointments Unit of Work: on commit, appointment events also become history rows (AP-8.1,
DR-4) - same transaction as the change, so state and history can never disagree."""

from __future__ import annotations

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.appointments.domain.events import AppointmentEvent
from app.modules.appointments.infrastructure.repositories import (
    SqlAppointmentHistory,
    SqlAppointmentRepository,
    SqlCaseRepository,
    SqlDeletionRequestRepository,
    SqlDoctorRepository,
    SqlPatientRepository,
    SqlSlotReservations,
)
from app.modules.appointments.infrastructure.tables import appointment_events
from app.shared.infrastructure.serialization import serialize_event
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork
from app.shared.kernel.events import DomainEvent
from app.shared.kernel.ids import IdGenerator, TenantId


class SqlAppointmentsUnitOfWork(SqlUnitOfWork):
    doctors: SqlDoctorRepository
    patients: SqlPatientRepository
    cases: SqlCaseRepository
    appointments: SqlAppointmentRepository
    reservations: SqlSlotReservations
    history: SqlAppointmentHistory
    deletion_requests: SqlDeletionRequestRepository

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        tenant_id: TenantId,
        ids: IdGenerator,
    ) -> None:
        super().__init__(session_factory, tenant_id)
        self._tenant, self._ids = tenant_id, ids

    def _create_repositories(self) -> None:
        self.doctors = SqlDoctorRepository(self.session, self)
        self.patients = SqlPatientRepository(self.session, self)
        self.cases = SqlCaseRepository(self.session, self)
        self.appointments = SqlAppointmentRepository(self.session, self)
        self.reservations = SqlSlotReservations(self.session, self._tenant, self._ids)
        self.history = SqlAppointmentHistory(self.session)
        self.deletion_requests = SqlDeletionRequestRepository(self.session, self)

    async def _save_events(self, events: list[DomainEvent]) -> None:
        await super()._save_events(events)  # outbox
        rows = [
            {
                "id": e.event_id,
                "tenant_id": self._tenant,
                "appointment_id": e.appointment_id,
                "event_type": e.event_type,
                "actor": str(e.actor),
                "channel": e.channel.value,
                "payload": serialize_event(e),
                "occurred_at": e.occurred_at,
            }
            for e in events
            if isinstance(e, AppointmentEvent)
        ]
        if rows:
            await self.session.execute(insert(appointment_events), rows)
