"""Login / refresh / logout use cases with fakes."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from app.platform.identity.application.commands.login import Login, LoginCommand
from app.platform.identity.application.commands.logout import Logout
from app.platform.identity.application.commands.members import AddMember, AddMemberCommand
from app.platform.identity.application.commands.refresh_session import (
    RefreshSessionCommand,
    RefreshUserSession,
)
from app.platform.identity.application.sessions import SessionIssuer
from app.platform.identity.domain.errors import (
    InvalidCredentialsError,
    NotAMemberError,
    RefreshTokenInvalidError,
)
from app.platform.identity.tests.fakes import (
    FakeDirectory,
    FakeHasher,
    FakeTokens,
    InMemoryIdentityUnitOfWork,
)
from app.shared.application.permissions import PermissionRegistry
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role
from app.shared.testing.fakes import FixedClock, SequentialIds

CLINIC_A = TenantId(UUID(int=0xA))
CLINIC_B = TenantId(UUID(int=0xB))
PASSWORD = "correct horse battery"


class World:
    def __init__(self) -> None:
        self.clock = FixedClock()
        self.ids = SequentialIds()
        self.uow = InMemoryIdentityUnitOfWork()
        self.hasher = FakeHasher()
        self.tokens = FakeTokens(self.clock)
        permissions = PermissionRegistry()
        permissions.register({"contact.read": "x"}, {Role.STAFF: {"contact.read"}})
        self.sessions = SessionIssuer(
            self.tokens,
            permissions,
            FakeDirectory({CLINIC_A: "Clinic A", CLINIC_B: "Clinic B"}),
            self.clock,
            self.ids,
            timedelta(days=14),
        )
        self.login = Login(self.uow, self.hasher, self.sessions)
        self.refresh = RefreshUserSession(self.uow, self.sessions, self.clock)
        self.logout = Logout(self.uow, self.clock)

    async def add_member(self, tenant: TenantId, role: Role, email: str = "s@x.com") -> None:
        await AddMember(self.uow, self.hasher, self.clock, self.ids)(
            AddMemberCommand(tenant, email, "Staff", role, Actor.system(), PASSWORD)
        )


@pytest.fixture
def world() -> World:
    return World()


async def test_login_issues_tokens_for_first_tenant(world: World) -> None:
    await world.add_member(CLINIC_A, Role.STAFF)

    session = await world.login(LoginCommand("S@X.com", PASSWORD))

    assert session.me.active_tenant_id == CLINIC_A
    assert session.me.permissions == ["contact.read"]
    assert session.me.memberships[0].tenant_name == "Clinic A"
    assert session.refresh_token  # raw token for the cookie


async def test_wrong_password_and_unknown_email_look_the_same(world: World) -> None:
    await world.add_member(CLINIC_A, Role.STAFF)

    with pytest.raises(InvalidCredentialsError):
        await world.login(LoginCommand("s@x.com", "wrong password!"))
    with pytest.raises(InvalidCredentialsError):
        await world.login(LoginCommand("nobody@x.com", PASSWORD))
    assert world.hasher.dummy_calls == 1  # unknown email still spends hashing time


async def test_login_into_foreign_tenant_is_refused(world: World) -> None:
    await world.add_member(CLINIC_A, Role.STAFF)
    with pytest.raises(NotAMemberError):
        await world.login(LoginCommand("s@x.com", PASSWORD, tenant_id=CLINIC_B))


async def test_refresh_rotates_and_switches_tenant(world: World) -> None:
    await world.add_member(CLINIC_A, Role.STAFF)
    await world.add_member(CLINIC_B, Role.ADMIN)
    first = await world.login(LoginCommand("s@x.com", PASSWORD))

    second = await world.refresh(RefreshSessionCommand(first.refresh_token, CLINIC_B))

    assert second.refresh_token != first.refresh_token
    assert second.me.active_tenant_id == CLINIC_B
    assert second.me.role is Role.ADMIN


async def test_reusing_a_rotated_token_ends_the_whole_session(world: World) -> None:
    await world.add_member(CLINIC_A, Role.STAFF)
    first = await world.login(LoginCommand("s@x.com", PASSWORD))
    second = await world.refresh(RefreshSessionCommand(first.refresh_token))

    with pytest.raises(RefreshTokenInvalidError):  # attacker replays the old token
        await world.refresh(RefreshSessionCommand(first.refresh_token))
    with pytest.raises(RefreshTokenInvalidError):  # ...so the legit newer one dies too
        await world.refresh(RefreshSessionCommand(second.refresh_token))


async def test_expired_refresh_token_is_rejected(world: World) -> None:
    await world.add_member(CLINIC_A, Role.STAFF)
    session = await world.login(LoginCommand("s@x.com", PASSWORD))
    world.clock.advance(timedelta(days=15))

    with pytest.raises(RefreshTokenInvalidError):
        await world.refresh(RefreshSessionCommand(session.refresh_token))


async def test_logout_revokes_refresh_token(world: World) -> None:
    await world.add_member(CLINIC_A, Role.STAFF)
    session = await world.login(LoginCommand("s@x.com", PASSWORD))

    await world.logout(session.refresh_token)

    with pytest.raises(RefreshTokenInvalidError):
        await world.refresh(RefreshSessionCommand(session.refresh_token))


async def test_outdated_hash_is_upgraded_on_login(world: World) -> None:
    await world.add_member(CLINIC_A, Role.STAFF)
    world.hasher.outdated.add(f"hashed:{PASSWORD}")

    await world.login(LoginCommand("s@x.com", PASSWORD))

    [user] = world.uow.users.rows.values()
    assert user.version == 1  # saved once by the upgrade
