from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.platform.identity.application.ports import PasswordHasher
from app.platform.identity.application.unit_of_work import IdentityUnitOfWork
from app.platform.identity.domain.errors import InvalidCredentialsError
from app.platform.identity.domain.user import check_password_strength
from app.shared.kernel.clock import Clock


@dataclass(frozen=True)
class ChangePasswordCommand:
    user_id: UUID
    current_password: str
    new_password: str


class ChangePassword:
    def __init__(self, uow: IdentityUnitOfWork, hasher: PasswordHasher, clock: Clock) -> None:
        self._uow, self._hasher, self._clock = uow, hasher, clock

    async def __call__(self, cmd: ChangePasswordCommand) -> None:
        check_password_strength(cmd.new_password)
        async with self._uow as uow:
            user = await uow.users.get(cmd.user_id)
            if not self._hasher.verify(cmd.current_password, user.password_hash):
                raise InvalidCredentialsError("Current password is wrong")
            user.change_password_hash(self._hasher.hash(cmd.new_password), at=self._clock.now())
            await uow.users.save(user)
            await uow.commit()
