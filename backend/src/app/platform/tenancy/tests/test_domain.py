from __future__ import annotations

from uuid import UUID

import pytest

from app.platform.tenancy.domain.errors import (
    InvalidPhoneNumberIdError,
    InvalidSlugError,
    InvalidTimezoneError,
    ModuleNotEnabledError,
)
from app.platform.tenancy.domain.events import ModuleEnabled, TenantCreated
from app.platform.tenancy.domain.tenant import Tenant, TenantStatus
from app.platform.tenancy.domain.whatsapp_number import WhatsAppNumber
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.testing.fakes import FixedClock

NOW = FixedClock().now()
OPERATOR = Actor.system()


def make_tenant(**overrides: str) -> Tenant:
    args = {"name": "Sunrise Clinic", "slug": "sunrise-clinic", "timezone": "Asia/Kolkata"}
    args.update(overrides)
    return Tenant.create(id=UUID(int=1), actor=OPERATOR, at=NOW, **args)


def test_create_records_event() -> None:
    tenant = make_tenant()
    assert tenant.is_active
    assert [type(e) for e in tenant.pull_events()] == [TenantCreated]


@pytest.mark.parametrize("slug", ["ab", "Has Space", "-dash-first", "x" * 41, "under_score"])
def test_invalid_slugs(slug: str) -> None:
    with pytest.raises(InvalidSlugError):
        make_tenant(slug=slug)


def test_unknown_timezone() -> None:
    with pytest.raises(InvalidTimezoneError):
        make_tenant(timezone="Mars/Olympus")


def test_modules_enable_once_and_settings_need_enabled_module() -> None:
    tenant = make_tenant()
    tenant.pull_events()

    tenant.enable_module("appointments", actor=OPERATOR, at=NOW)
    tenant.enable_module("appointments", actor=OPERATOR, at=NOW)  # no-op
    tenant.update_module_settings("appointments", {"approval": True}, actor=OPERATOR, at=NOW)

    assert tenant.modules == {"appointments": {"approval": True}}
    assert [type(e) for e in tenant.pull_events()].count(ModuleEnabled) == 1
    with pytest.raises(ModuleNotEnabledError):
        tenant.update_module_settings("surveys", {}, actor=OPERATOR, at=NOW)


def test_suspend() -> None:
    tenant = make_tenant()
    tenant.set_status(TenantStatus.SUSPENDED, actor=OPERATOR, at=NOW)
    assert not tenant.is_active


def test_phone_number_id_must_be_numeric() -> None:
    with pytest.raises(InvalidPhoneNumberIdError):
        WhatsAppNumber.connect(
            id=UUID(int=2),
            tenant_id=TenantId(UUID(int=1)),
            phone_number_id="abc",
            display_phone="+91",
            actor=OPERATOR,
            at=NOW,
        )
