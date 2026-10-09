"""Log out: revoke the whole refresh family of the presented token. Always succeeds."""

from __future__ import annotations

from app.platform.identity.application.sessions import hash_refresh_token
from app.platform.identity.application.unit_of_work import IdentityUnitOfWork
from app.shared.kernel.clock import Clock


class Logout:
    def __init__(self, uow: IdentityUnitOfWork, clock: Clock) -> None:
        self._uow, self._clock = uow, clock

    async def __call__(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        async with self._uow as uow:
            session = await uow.refresh_sessions.find_by_hash(hash_refresh_token(refresh_token))
            if session is not None:
                await uow.refresh_sessions.revoke_family(session.family_id, self._clock.now())
                await uow.commit()
