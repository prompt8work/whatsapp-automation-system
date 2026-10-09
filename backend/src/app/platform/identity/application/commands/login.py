"""Log in with email + password. Returns access token + refresh token (for the cookie)."""

from __future__ import annotations

from dataclasses import dataclass

from app.platform.identity.application.dto import SessionDTO
from app.platform.identity.application.ports import PasswordHasher
from app.platform.identity.application.sessions import SessionIssuer
from app.platform.identity.application.unit_of_work import IdentityUnitOfWork
from app.platform.identity.domain.errors import InvalidCredentialsError, NotAMemberError
from app.platform.identity.domain.user import normalize_email
from app.shared.kernel.errors import DomainError
from app.shared.kernel.ids import TenantId


@dataclass(frozen=True)
class LoginCommand:
    email: str
    password: str
    tenant_id: TenantId | None = None  # None: the user's first tenant


class Login:
    def __init__(
        self, uow: IdentityUnitOfWork, hasher: PasswordHasher, sessions: SessionIssuer
    ) -> None:
        self._uow, self._hasher, self._sessions = uow, hasher, sessions

    async def __call__(self, cmd: LoginCommand) -> SessionDTO:
        try:
            email = normalize_email(cmd.email)
        except DomainError as exc:
            raise InvalidCredentialsError() from exc

        async with self._uow as uow:
            user = await uow.users.find_by_email(email)
            if user is None:
                self._hasher.dummy_verify(cmd.password)
                raise InvalidCredentialsError()
            if not self._hasher.verify(cmd.password, user.password_hash) or not user.is_active:
                raise InvalidCredentialsError()

            if self._hasher.needs_rehash(user.password_hash):
                user.upgrade_password_hash(self._hasher.hash(cmd.password))
                await uow.users.save(user)

            tenant_id = cmd.tenant_id or user.default_tenant()
            if tenant_id is not None and user.role_in(tenant_id) is None:
                raise NotAMemberError()

            session, _ = await self._sessions.issue(uow, user, tenant_id)
            await uow.commit()
        return session
