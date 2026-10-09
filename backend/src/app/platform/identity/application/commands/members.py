"""Tenant admins manage who can use their dashboard (PRD §5, AP-7.7 "users").

Three small commands share a file because they are the same shape: load user -> one domain
method -> save. `AddMember` creates the user when the email is new; the admin hands the
initial password over (email invitations come later).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.platform.identity.application.dto import MemberDTO
from app.platform.identity.application.ports import PasswordHasher
from app.platform.identity.application.unit_of_work import IdentityUnitOfWork
from app.platform.identity.domain.errors import WeakPasswordError
from app.platform.identity.domain.user import User, check_password_strength, normalize_email
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator, TenantId
from app.shared.kernel.roles import Role


@dataclass(frozen=True)
class AddMemberCommand:
    tenant_id: TenantId
    email: str
    full_name: str
    role: Role
    actor: Actor
    initial_password: str | None = None  # required only if the email is new


class AddMember:
    def __init__(
        self, uow: IdentityUnitOfWork, hasher: PasswordHasher, clock: Clock, ids: IdGenerator
    ) -> None:
        self._uow, self._hasher, self._clock, self._ids = uow, hasher, clock, ids

    async def __call__(self, cmd: AddMemberCommand) -> MemberDTO:
        now = self._clock.now()
        email = normalize_email(cmd.email)
        async with self._uow as uow:
            user = await uow.users.find_by_email(email)
            if user is None:
                if not cmd.initial_password:
                    raise WeakPasswordError("New users need an initial password")
                check_password_strength(cmd.initial_password)
                user = User.create(
                    id=self._ids.new_id(),
                    email=email,
                    full_name=cmd.full_name,
                    password_hash=self._hasher.hash(cmd.initial_password),
                    actor=cmd.actor,
                    at=now,
                )
                user.grant_membership(cmd.tenant_id, cmd.role, actor=cmd.actor, at=now)
                await uow.users.add(user)
            else:
                user.grant_membership(cmd.tenant_id, cmd.role, actor=cmd.actor, at=now)
                await uow.users.save(user)
            await uow.commit()
        return MemberDTO.from_domain(user, cmd.tenant_id)


@dataclass(frozen=True)
class ChangeMemberRoleCommand:
    tenant_id: TenantId
    user_id: UUID
    role: Role
    actor: Actor


class ChangeMemberRole:
    def __init__(self, uow: IdentityUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: ChangeMemberRoleCommand) -> MemberDTO:
        async with self._uow as uow:
            user = await uow.users.get(cmd.user_id)
            user.change_role(cmd.tenant_id, cmd.role, actor=cmd.actor, at=self._clock.now())
            await uow.users.save(user)
            await uow.commit()
        return MemberDTO.from_domain(user, cmd.tenant_id)


@dataclass(frozen=True)
class RemoveMemberCommand:
    tenant_id: TenantId
    user_id: UUID
    actor: Actor


class RemoveMember:
    def __init__(self, uow: IdentityUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, cmd: RemoveMemberCommand) -> None:
        async with self._uow as uow:
            user = await uow.users.get(cmd.user_id)
            user.revoke_membership(cmd.tenant_id, actor=cmd.actor, at=self._clock.now())
            await uow.users.save(user)
            await uow.commit()
