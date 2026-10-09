from __future__ import annotations

from app.platform.identity.application.dto import MeDTO
from app.platform.identity.application.ports import TenantDirectory
from app.platform.identity.application.sessions import describe
from app.platform.identity.application.unit_of_work import IdentityUnitOfWork
from app.shared.application.auth import Principal


class GetMe:
    def __init__(self, uow: IdentityUnitOfWork, directory: TenantDirectory) -> None:
        self._uow, self._directory = uow, directory

    async def __call__(self, principal: Principal) -> MeDTO:
        async with self._uow as uow:
            user = await uow.users.get(principal.user_id)
        return await describe(user, principal, self._directory)
