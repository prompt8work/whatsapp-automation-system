from __future__ import annotations

from typing import Protocol

from app.modules.appointments.domain.repositories import (
    AppointmentHistory,
    AppointmentRepository,
    CaseRepository,
    DoctorRepository,
    PatientRepository,
    SlotReservations,
)
from app.shared.application.unit_of_work import UnitOfWork


class AppointmentsUnitOfWork(UnitOfWork, Protocol):
    @property
    def doctors(self) -> DoctorRepository: ...

    @property
    def patients(self) -> PatientRepository: ...

    @property
    def cases(self) -> CaseRepository: ...

    @property
    def appointments(self) -> AppointmentRepository: ...

    @property
    def reservations(self) -> SlotReservations: ...

    @property
    def history(self) -> AppointmentHistory: ...
