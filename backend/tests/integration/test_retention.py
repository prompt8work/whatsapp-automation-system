"""Retention and deletion (PRD §7.10) against PostgreSQL: the daily purge (RT-1..RT-6) and
patients deleting their data on request (AP-10.8..10.13)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from app.platform.retention.application.use_cases import RetentionRun, RunRetention
from app.platform.retention.integration import record_deletion_for
from app.shared.kernel.ids import TenantId
from app.shared.testing.fakes import FixedClock
from tests.integration.conftest import Api
from tests.integration.test_appointment_bot import Chat, book_tomorrow, clinic, tick

pytestmark = pytest.mark.db


@dataclasses.dataclass(frozen=True)
class OneTenant:
    tenant_id: TenantId

    async def all_tenant_ids(self) -> list[TenantId]:
        return [self.tenant_id]


async def run_retention(api: Api, tenant_id: TenantId, *, days_from_now: int) -> RetentionRun:
    """The daily job as it will run `days_from_now` days from now, for this tenant only (the
    shared test database holds other tests' tenants)."""
    later = FixedClock(datetime.now(UTC) + timedelta(days=days_from_now))
    services = dataclasses.replace(api.container, clock=later)
    modules = api.app.state.platform.modules
    purgers = [make(services) for module in reversed(modules) for make in module.purgers]
    run = RunRetention(OneTenant(tenant_id), purgers, record_deletion_for(services), later)
    return await run()


async def tenant_of(api: Api, headers: dict[str, str]) -> TenantId:
    me = (await api.client.get("/api/auth/me", headers=headers)).json()
    return TenantId(UUID(me["active_tenant_id"]))


async def booked_patient(api: Api) -> tuple[dict[str, str], Chat, dict[str, Any]]:
    """A new patient books on WhatsApp; returns (admin headers, chat, the appointment)."""
    admin, number = await clinic(api)
    chat = Chat(api, number)
    await chat.send("Hi")
    await chat.tap("Yes")
    await chat.send("Rahul Verma")
    await book_tomorrow(chat)
    [appointment] = (await api.client.get("/api/appointments/requests", headers=admin)).json()
    return admin, chat, appointment


async def close_case(api: Api, admin: dict[str, str], appointment: dict[str, Any]) -> str:
    cancel = await api.client.post(
        f"/api/appointments/{appointment['id']}/cancel", json={"reason": ""}, headers=admin
    )
    assert cancel.status_code == 200, cancel.text
    case_id: str = appointment["case_id"]
    closed = await api.client.post(f"/api/cases/{case_id}/close", json={}, headers=admin)
    assert closed.status_code == 200, closed.text
    return case_id


async def test_closed_case_is_deleted_after_60_days_then_the_contact(api: Api) -> None:
    admin, chat, appointment = await booked_patient(api)
    tenant_id = await tenant_of(api, admin)
    case_id = await close_case(api, admin, appointment)

    [case] = (
        await api.client.get(f"/api/patients/{appointment['patient_id']}/cases", headers=admin)
    ).json()
    deletes_at = datetime.fromisoformat(case["deletes_at"])
    assert timedelta(days=59) < deletes_at - datetime.now(UTC) <= timedelta(days=60)  # AP-10.6

    assert (await run_retention(api, tenant_id, days_from_now=59)).purged == 0
    run = await run_retention(api, tenant_id, days_from_now=61)
    assert run == RetentionRun(purged=2, failed=0)  # the case (RT-1), then the contact (RT-4)

    gone = await api.client.get(f"/api/appointments/{appointment['id']}", headers=admin)
    assert gone.status_code == 404
    records = (await api.client.get("/api/retention/records", headers=admin)).json()
    by_rule = {r["rule"]: r for r in records}
    assert by_rule["RT-1"]["subject_id"] == case_id
    assert by_rule["RT-1"]["counts"] == {
        "cases": 1,
        "appointments": 1,
        "history_events": 2,  # requested, cancelled
        "patients": 1,
    }
    assert by_rule["RT-4"]["counts"] == {"contacts": 1}
    assert "Rahul" not in str(records)  # AP-10.5: no personal data

    await tick(api)  # ContactForgotten -> message log, session, handovers deleted
    assert (await api.client.get("/api/inbox", headers=admin)).json() == []

    # The number writes again: a brand-new contact, welcomed like the first time (R1).
    [welcome, _] = await chat.send("Hi")
    assert "Welcome!" in welcome


async def test_legal_hold_and_active_appointments_block_the_purge(api: Api) -> None:  # RT-6
    admin, _, appointment = await booked_patient(api)
    tenant_id = await tenant_of(api, admin)
    # An OPEN case with an active (requested) appointment is never due, however old.
    assert (await run_retention(api, tenant_id, days_from_now=400)).purged == 0

    case_id = await close_case(api, admin, appointment)
    hold = await api.client.put(
        f"/api/cases/{case_id}/legal-hold", json={"hold": True}, headers=admin
    )
    assert hold.json()["legal_hold"] is True
    assert (await run_retention(api, tenant_id, days_from_now=400)).purged == 0
    [case] = (
        await api.client.get(f"/api/patients/{appointment['patient_id']}/cases", headers=admin)
    ).json()
    assert case["deletes_at"] is None


async def test_upcoming_deletions_follow_the_clinic_setting(api: Api) -> None:  # AP-10.6/10.7
    admin, _, appointment = await booked_patient(api)
    case_id = await close_case(api, admin, appointment)
    assert (await api.client.get("/api/retention/upcoming", headers=admin)).json() == []

    rules = (await api.client.get("/api/appointments/settings", headers=admin)).json()
    saved = await api.client.put(
        "/api/appointments/settings", json=rules | {"retention_closed_days": 3}, headers=admin
    )
    assert saved.status_code == 200, saved.text
    [upcoming] = (await api.client.get("/api/retention/upcoming", headers=admin)).json()
    assert (upcoming["subject_id"], upcoming["rule"], upcoming["label"]) == (
        case_id,
        "RT-1",
        "Rahul Verma",
    )

    reopened = await api.client.post(f"/api/cases/{case_id}/reopen", headers=admin)  # RT-5
    assert reopened.status_code == 200
    assert (await api.client.get("/api/retention/upcoming", headers=admin)).json() == []


async def test_patient_deletes_their_data_on_request(api: Api) -> None:  # AP-10.8..10.13
    admin, chat, appointment = await booked_patient(api)

    [explain] = await chat.send("DELETE MY DATA")  # works from anywhere
    assert "This deletes Rahul Verma" in explain
    assert "Payment records are NOT deleted" in explain
    [sent] = await chat.tap("Yes, delete")
    assert "Request sent ✅" in sent
    [already] = await chat.send("delete my data")
    assert "already asked" in already

    [request] = (
        await api.client.get("/api/deletion-requests?status=pending", headers=admin)
    ).json()
    assert request["patients"] == [{"id": appointment["patient_id"], "name": "Rahul Verma"}]

    approved = await api.client.post(
        f"/api/deletion-requests/{request['id']}/approve", headers=admin
    )
    assert approved.status_code == 200, approved.text
    done = approved.json()
    assert done["status"] == "completed"
    assert done["patients"] == [{"id": appointment["patient_id"], "name": None}]
    assert done["deleted_counts"]["cancelled_appointments"] == 1  # the slot is free again
    assert done["deleted_counts"]["patients"] == 1

    gone = await api.client.get(f"/api/appointments/{appointment['id']}", headers=admin)
    assert gone.status_code == 404
    records = (await api.client.get("/api/retention/records", headers=admin)).json()
    assert [(r["rule"], r["subject_id"]) for r in records] == [
        ("AP-10.11", appointment["patient_id"])
    ]

    await tick(api)  # -> confirmation on WhatsApp; the cancellation notice is skipped
    assert "Your data has been deleted" in chat.inbox()[-1]
    assert not any("was cancelled by the clinic" in m for m in chat.inbox())

    [nothing] = await chat.send("delete my data")
    assert "We don't keep any patient details" in nothing


async def test_staff_reject_a_deletion_request_with_a_reason(api: Api) -> None:  # AP-10.10
    admin, chat, _ = await booked_patient(api)
    [menu] = await chat.send("Hi")
    assert "Delete my data" in menu
    await chat.tap("Delete my data")
    await chat.tap("Yes, delete")
    [request] = (await api.client.get("/api/deletion-requests", headers=admin)).json()

    url = f"/api/deletion-requests/{request['id']}/reject"
    assert (await api.client.post(url, json={"reason": ""}, headers=admin)).status_code == 422
    rejected = await api.client.post(
        url, json={"reason": "Your visit tomorrow must be cancelled first."}, headers=admin
    )
    assert rejected.json()["status"] == "rejected"
    again = await api.client.post(f"/api/deletion-requests/{request['id']}/approve", headers=admin)
    assert again.status_code == 409

    await tick(api)
    assert "Your visit tomorrow must be cancelled first." in chat.inbox()[-1]
