"""Event handler: when a request (or a reschedule request) is made, schedule its expiry job.

Done from the outbox rather than inside the booking transaction, so a request is NEVER left
without its expiry (the outbox delivers at least once; the idempotency key stops duplicates).
"""

from __future__ import annotations

from uuid import UUID

from app.modules.appointments.application.commands.decisions import (
    EXPIRE_REQUEST_JOB,
    EXPIRE_RESCHEDULE_JOB,
)
from app.modules.appointments.application.ports import ClinicDirectory
from app.modules.appointments.domain.policy import BookingPolicy
from app.shared.application.events import StoredEvent
from app.shared.application.jobs import JobScheduler, ScheduleJob


class ScheduleExpiry:
    def __init__(self, jobs: JobScheduler, clinic: ClinicDirectory) -> None:
        self._jobs, self._clinic = jobs, clinic

    async def __call__(self, event: StoredEvent) -> None:
        assert event.tenant_id is not None
        if event.event_type == "AppointmentRequested":
            if not event.payload.get("needs_approval"):
                return
            job_type = EXPIRE_REQUEST_JOB
        else:  # RescheduleRequested
            job_type = EXPIRE_RESCHEDULE_JOB
        policy = BookingPolicy.from_settings(await self._clinic.settings(event.tenant_id))
        appointment_id = UUID(event.payload["appointment_id"])
        await self._jobs.schedule(
            ScheduleJob(
                job_type,
                event.occurred_at + policy.request_expiry,
                f"{job_type}:{event.event_id}",
                tenant_id=event.tenant_id,
                payload={"appointment_id": str(appointment_id)},
            )
        )
