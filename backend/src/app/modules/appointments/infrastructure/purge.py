"""Retention purge of cases (PRD §7.10) - hard delete, as role `app_purge`.

One case at a time, in its own transaction:
  appointments of the case (their history events and slot holds go by ON DELETE CASCADE),
  then the case, then the patient once they have no cases left (RT-3).
The contact is NOT touched here: once no patient points at it, the contacts purger (RT-4)
takes it when it has been quiet for 60 days.

Never purged (RT-6): a case on legal hold, with an active appointment, or with a PENDING payment
(asked from payments). Everything is re-checked under a row lock, so a case reopened since
`due` is left alone. Payments themselves are never deleted: CasePurged carries the appointment
ids, and payments detach their records into the ledger (RT-7).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, exists, func, not_, select
from sqlalchemy import case as sql_case
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.appointments.domain.events import CasePurged
from app.modules.appointments.domain.policy import BookingPolicy
from app.modules.appointments.domain.status import ACTIVE
from app.modules.appointments.infrastructure.tables import (
    appointment_events,
    appointments,
    cases,
    patients,
)
from app.shared.application.payments import Payments
from app.shared.application.retention import PurgeResult, PurgeTarget
from app.shared.infrastructure.unit_of_work import SqlUnitOfWork
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import TenantId

CLOSED_RULE, IDLE_RULE, REQUEST_RULE = "RT-1", "RT-2", "AP-10.11"

SettingsReader = Callable[[TenantId], Awaitable[dict[str, Any]]]

_no_active = not_(
    exists().where(
        appointments.c.case_id == cases.c.id,
        appointments.c.status.in_([s.value for s in ACTIVE]),
    )
)


def _due_at(policy: BookingPolicy) -> Any:
    """SQL expression: when the case becomes due for deletion (RT-1 closed / RT-2 open)."""
    return sql_case(
        (cases.c.status == "closed", cases.c.closed_at + policy.retention_closed),
        else_=cases.c.last_activity_at + policy.retention_open,
    )


class CasePurger:
    key = "appointments.cases"

    def __init__(
        self,
        purge_sessions: async_sessionmaker[AsyncSession],
        settings: SettingsReader,
        clock: Clock,
        payments: Payments,
    ) -> None:
        self._sessions, self._settings, self._clock = purge_sessions, settings, clock
        self._payments = payments

    async def _unpaid_cases(self, tenant_id: TenantId, case_ids: list[UUID]) -> set[UUID]:
        """RT-6: cases with an appointment whose payment is still PENDING."""
        if not case_ids:
            return set()
        async with SqlUnitOfWork(self._sessions, tenant_id) as uow:
            rows = (
                await uow.session.execute(
                    select(appointments.c.id, appointments.c.case_id).where(
                        appointments.c.case_id.in_(case_ids)
                    )
                )
            ).all()
        case_of = {r.id: r.case_id for r in rows}
        unpaid = await self._payments.unsettled(tenant_id, "appointment", list(case_of))
        return {case_of[a] for a in unpaid}

    async def _policy(self, tenant_id: TenantId) -> BookingPolicy:
        return BookingPolicy.from_settings(await self._settings(tenant_id))

    async def due(self, tenant_id: TenantId, until: datetime) -> list[PurgeTarget]:
        due_at = _due_at(await self._policy(tenant_id))
        stmt = (
            select(cases.c.id, cases.c.status, due_at.label("due_at"), patients.c.full_name)
            .join(patients, patients.c.id == cases.c.patient_id)
            .where(not_(cases.c.legal_hold), due_at <= until, _no_active)
            .order_by(due_at)
        )
        async with SqlUnitOfWork(self._sessions, tenant_id) as uow:
            rows = (await uow.session.execute(stmt)).all()
        unpaid = await self._unpaid_cases(tenant_id, [r.id for r in rows])
        return [
            PurgeTarget(
                "case",
                r.id,
                CLOSED_RULE if r.status == "closed" else IDLE_RULE,
                r.due_at,
                label=r.full_name,
            )
            for r in rows
            if r.id not in unpaid
        ]

    async def purge(self, tenant_id: TenantId, target: PurgeTarget) -> PurgeResult:
        policy = await self._policy(tenant_id)
        still_due = None if target.rule == REQUEST_RULE else _due_at(policy) <= self._clock.now()
        return await self._purge_case(tenant_id, target.subject_id, target.rule, still_due)

    async def purge_patient(self, tenant_id: TenantId, patient_id: UUID) -> PurgeResult:
        """On request (AP-10.11): every case of the patient, then the patient - now.
        Active appointments must be cancelled first; a legal hold blocks it (empty result)."""
        async with SqlUnitOfWork(self._sessions, tenant_id) as uow:
            case_ids = list(
                (
                    await uow.session.execute(
                        select(cases.c.id).where(cases.c.patient_id == patient_id)
                    )
                ).scalars()
            )
        total: dict[str, int] = {}
        for case_id in case_ids:
            result = await self._purge_case(tenant_id, case_id, REQUEST_RULE, None)
            if not result.counts:
                return PurgeResult(total)  # blocked: stop, the patient must stay
            for k, v in result.counts.items():
                total[k] = total.get(k, 0) + v
        if not case_ids:  # registered but never booked
            async with SqlUnitOfWork(self._sessions, tenant_id) as uow:
                total["patients"] = await self._delete_patient_if_free(uow, patient_id)
                await uow.commit()
        return PurgeResult(total)

    async def _purge_case(
        self, tenant_id: TenantId, case_id: UUID, rule: str, still_due: Any | None
    ) -> PurgeResult:
        if await self._unpaid_cases(tenant_id, [case_id]):
            return PurgeResult()  # RT-6: a payment is still pending
        async with SqlUnitOfWork(self._sessions, tenant_id) as uow:
            s = uow.session
            conditions = [cases.c.id == case_id, not_(cases.c.legal_hold), _no_active]
            if still_due is not None:
                conditions.append(still_due)
            row = (
                await s.execute(
                    select(cases.c.patient_id).where(and_(*conditions)).with_for_update()
                )
            ).first()
            if row is None:  # reopened, put on hold, booked again, or already gone
                return PurgeResult()
            patient_id: UUID = row.patient_id
            of_case = select(appointments.c.id).where(appointments.c.case_id == case_id)
            events = await s.scalar(
                select(func.count()).where(appointment_events.c.appointment_id.in_(of_case))
            )
            gone = await s.execute(
                delete(appointments)
                .where(appointments.c.case_id == case_id)
                .returning(appointments.c.id)
            )
            appointment_ids = tuple(r.id for r in gone.all())
            await s.execute(delete(cases).where(cases.c.id == case_id))
            n_patients = await self._delete_patient_if_free(uow, patient_id)
            uow.publish(
                CasePurged(
                    occurred_at=self._clock.now(),
                    case_id=case_id,
                    patient_id=patient_id,
                    patient_deleted=bool(n_patients),
                    rule=rule,
                    appointment_ids=appointment_ids,
                )
            )
            await uow.commit()
        return PurgeResult(
            {
                "cases": 1,
                "appointments": len(appointment_ids),
                "history_events": int(events or 0),
                "patients": n_patients,
            }
        )

    @staticmethod
    async def _delete_patient_if_free(uow: SqlUnitOfWork, patient_id: UUID) -> int:
        """RT-3: the patient profile goes with their last case."""
        gone = await uow.session.execute(
            delete(patients)
            .where(
                patients.c.id == patient_id,
                not_(exists().where(cases.c.patient_id == patient_id)),
                not_(exists().where(appointments.c.patient_id == patient_id)),
            )
            .returning(patients.c.id)
        )
        return len(gone.all())
