from __future__ import annotations

from uuid import UUID

import pytest

from app.platform.identity.domain.errors import (
    AlreadyMemberError,
    CannotChangeOwnMembershipError,
    InvalidEmailError,
    WeakPasswordError,
)
from app.platform.identity.domain.events import MembershipGranted, MembershipRoleChanged
from app.platform.identity.domain.user import User, check_password_strength, normalize_email
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role
from app.shared.testing.fakes import FixedClock

NOW = FixedClock().now()
CLINIC = TenantId(UUID(int=50))
ADMIN = Actor.staff(UUID(int=99))


def make_user() -> User:
    user = User.create(
        id=UUID(int=1),
        email="  Dr.Amit@Example.COM ",
        full_name="Dr  Amit",
        password_hash="h",
        actor=ADMIN,
        at=NOW,
    )
    user.pull_events()
    return user


def test_email_is_normalised() -> None:
    assert make_user().email == "dr.amit@example.com"


@pytest.mark.parametrize("bad", ["", "no-at-sign", "a@b", "two@@x.com"])
def test_invalid_emails_rejected(bad: str) -> None:
    with pytest.raises(InvalidEmailError):
        normalize_email(bad)


def test_short_password_rejected() -> None:
    with pytest.raises(WeakPasswordError):
        check_password_strength("short")


def test_membership_lifecycle_records_events() -> None:
    user = make_user()

    user.grant_membership(CLINIC, Role.STAFF, actor=ADMIN, at=NOW)
    user.change_role(CLINIC, Role.ADMIN, actor=ADMIN, at=NOW)

    assert user.role_in(CLINIC) is Role.ADMIN
    assert [type(e) for e in user.pull_events()] == [MembershipGranted, MembershipRoleChanged]


def test_cannot_join_twice() -> None:
    user = make_user()
    user.grant_membership(CLINIC, Role.STAFF, actor=ADMIN, at=NOW)
    with pytest.raises(AlreadyMemberError):
        user.grant_membership(CLINIC, Role.DOCTOR, actor=ADMIN, at=NOW)


def test_admin_cannot_demote_or_remove_themselves() -> None:
    user = make_user()
    user.grant_membership(CLINIC, Role.ADMIN, actor=ADMIN, at=NOW)
    myself = Actor.staff(user.id)
    with pytest.raises(CannotChangeOwnMembershipError):
        user.change_role(CLINIC, Role.STAFF, actor=myself, at=NOW)
    with pytest.raises(CannotChangeOwnMembershipError):
        user.revoke_membership(CLINIC, actor=myself, at=NOW)
