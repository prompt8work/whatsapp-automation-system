"""/api/auth/* (session) and /api/users/* (tenant members).

The refresh token travels ONLY in an httpOnly, SameSite=Strict cookie scoped to /api/auth,
so page JavaScript can never read it. The short-lived access token is returned in the body
and kept in memory by the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Response, status

from app.platform.identity.application.commands.change_password import ChangePasswordCommand
from app.platform.identity.application.commands.login import LoginCommand
from app.platform.identity.application.commands.members import (
    AddMemberCommand,
    ChangeMemberRoleCommand,
    RemoveMemberCommand,
)
from app.platform.identity.application.commands.refresh_session import RefreshSessionCommand
from app.platform.identity.application.dto import SessionDTO
from app.platform.identity.application.use_cases import IdentityUseCases
from app.platform.identity.domain.errors import RefreshTokenInvalidError
from app.platform.identity.presentation.http.schemas import (
    AddMemberRequest,
    ChangeMemberRoleRequest,
    ChangePasswordRequest,
    LoginRequest,
    MemberResponse,
    MeResponse,
    RefreshRequest,
    SessionResponse,
)
from app.shared.kernel.ids import TenantId
from app.shared.presentation.request_context import PrincipalDep, RequestContext, require

REFRESH_COOKIE = "refresh_token"
COOKIE_PATH = "/api/auth"

HTTP_ERROR_STATUS = {
    "identity.invalid_credentials": status.HTTP_401_UNAUTHORIZED,
    "identity.refresh_invalid": status.HTTP_401_UNAUTHORIZED,
    "identity.invalid_email": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "identity.weak_password": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "identity.email_taken": status.HTTP_409_CONFLICT,
    "identity.user_not_found": status.HTTP_404_NOT_FOUND,
    "identity.already_member": status.HTTP_409_CONFLICT,
    "identity.not_a_member": status.HTTP_403_FORBIDDEN,
    "identity.cannot_change_self": status.HTTP_409_CONFLICT,
}

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]
CanRead = Annotated[RequestContext, Depends(require("users.read"))]
CanManage = Annotated[RequestContext, Depends(require("users.manage"))]


@dataclass(frozen=True)
class CookieSettings:
    secure: bool  # False only for local http://localhost


def build_router(use_cases: IdentityUseCases, cookies: CookieSettings) -> APIRouter:
    router = APIRouter()  # mounted under /api by the app factory

    def set_session_cookie(response: Response, session: SessionDTO) -> None:
        response.set_cookie(
            REFRESH_COOKIE,
            session.refresh_token,
            expires=session.refresh_expires_at,
            path=COOKIE_PATH,
            httponly=True,
            secure=cookies.secure,
            samesite="strict",
        )

    def clear_session_cookie(response: Response) -> None:
        response.delete_cookie(
            REFRESH_COOKIE, path=COOKIE_PATH, secure=cookies.secure, httponly=True
        )

    # ------------------------------------------------------------------ session
    @router.post("/auth/login", tags=["auth"])
    async def login(body: LoginRequest, response: Response) -> SessionResponse:
        session = await use_cases.login(
            LoginCommand(
                email=body.email,
                password=body.password,
                tenant_id=TenantId(body.tenant_id) if body.tenant_id else None,
            )
        )
        set_session_cookie(response, session)
        return SessionResponse.from_dto(session)

    @router.post("/auth/refresh", tags=["auth"])
    async def refresh(
        response: Response,
        refresh_token: RefreshCookie = None,
        body: RefreshRequest | None = None,
    ) -> SessionResponse:
        if not refresh_token:
            raise RefreshTokenInvalidError("Not logged in")
        tenant = body.tenant_id if body else None
        try:
            session = await use_cases.refresh(
                RefreshSessionCommand(
                    refresh_token=refresh_token,
                    switch_to_tenant=TenantId(tenant) if tenant else None,
                )
            )
        except RefreshTokenInvalidError:
            clear_session_cookie(response)
            raise
        set_session_cookie(response, session)
        return SessionResponse.from_dto(session)

    @router.post("/auth/logout", tags=["auth"], status_code=status.HTTP_204_NO_CONTENT)
    async def logout(response: Response, refresh_token: RefreshCookie = None) -> None:
        await use_cases.logout(refresh_token)
        clear_session_cookie(response)

    @router.get("/auth/me", tags=["auth"])
    async def me(principal: PrincipalDep) -> MeResponse:
        return MeResponse.from_dto(await use_cases.get_me(principal))

    @router.post("/auth/password", tags=["auth"], status_code=status.HTTP_204_NO_CONTENT)
    async def change_password(body: ChangePasswordRequest, principal: PrincipalDep) -> None:
        await use_cases.change_password(
            ChangePasswordCommand(
                user_id=principal.user_id,
                current_password=body.current_password,
                new_password=body.new_password,
            )
        )

    # ------------------------------------------------------------------ members
    @router.get("/users", tags=["users"])
    async def list_members(ctx: CanRead) -> list[MemberResponse]:
        return [MemberResponse.from_dto(m) for m in await use_cases.list_members(ctx.tenant_id)]

    @router.post("/users", tags=["users"], status_code=status.HTTP_201_CREATED)
    async def add_member(body: AddMemberRequest, ctx: CanManage) -> MemberResponse:
        member = await use_cases.add_member(
            AddMemberCommand(
                tenant_id=ctx.tenant_id,
                email=body.email,
                full_name=body.full_name,
                role=body.role,
                actor=ctx.actor,
                initial_password=body.initial_password,
            )
        )
        return MemberResponse.from_dto(member)

    @router.patch("/users/{user_id}", tags=["users"])
    async def change_role(
        user_id: UUID, body: ChangeMemberRoleRequest, ctx: CanManage
    ) -> MemberResponse:
        member = await use_cases.change_member_role(
            ChangeMemberRoleCommand(
                tenant_id=ctx.tenant_id, user_id=user_id, role=body.role, actor=ctx.actor
            )
        )
        return MemberResponse.from_dto(member)

    @router.delete("/users/{user_id}", tags=["users"], status_code=status.HTTP_204_NO_CONTENT)
    async def remove_member(user_id: UUID, ctx: CanManage) -> None:
        await use_cases.remove_member(
            RemoveMemberCommand(tenant_id=ctx.tenant_id, user_id=user_id, actor=ctx.actor)
        )

    return router
