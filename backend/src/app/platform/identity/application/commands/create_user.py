"""Create a user with no tenant access (CLI: first super-admin; later: platform admin UI)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.platform.identity.application.ports import PasswordHasher
from app.platform.identity.application.unit_of_work import IdentityUnitOfWork
from app.platform.identity.domain.errors import EmailAlreadyUsedError
from app.platform.identity.domain.user import User, check_password_strength, normalize_email
from app.shared.kernel.actor import Actor
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator


@dataclass(frozen=True)
class CreateUserCommand:
    email: str
    full_name: str
    password: str
    actor: Actor
    is_super_admin: bool = False


class CreateUser:
    def __init__(
        self, uow: IdentityUnitOfWork, hasher: PasswordHasher, clock: Clock, ids: IdGenerator
    ) -> None:
        self._uow, self._hasher, self._clock, self._ids = uow, hasher, clock, ids

    async def __call__(self, cmd: CreateUserCommand) -> UUID:
        check_password_strength(cmd.password)
        email = normalize_email(cmd.email)
        async with self._uow as uow:
            if await uow.users.find_by_email(email) is not None:
                raise EmailAlreadyUsedError()
            user = User.create(
                id=self._ids.new_id(),
                email=email,
                full_name=cmd.full_name,
                password_hash=self._hasher.hash(cmd.password),
                actor=cmd.actor,
                at=self._clock.now(),
                is_super_admin=cmd.is_super_admin,
            )
            await uow.users.add(user)
            await uow.commit()
        return user.id
