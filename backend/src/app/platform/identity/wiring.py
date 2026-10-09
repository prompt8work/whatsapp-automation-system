"""Identity wiring. Unlike feature modules it needs more than PlatformServices (hasher,
token issuer, tenant directory), so bootstrap calls `build_identity` explicitly."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter

from app.platform.identity.application.commands.change_password import ChangePassword
from app.platform.identity.application.commands.create_user import CreateUser
from app.platform.identity.application.commands.login import Login
from app.platform.identity.application.commands.logout import Logout
from app.platform.identity.application.commands.members import (
    AddMember,
    ChangeMemberRole,
    RemoveMember,
)
from app.platform.identity.application.commands.refresh_session import RefreshUserSession
from app.platform.identity.application.ports import (
    AccessTokenIssuer,
    PasswordHasher,
    TenantDirectory,
)
from app.platform.identity.application.queries.get_me import GetMe
from app.platform.identity.application.queries.list_members import ListMembers
from app.platform.identity.application.sessions import SessionIssuer
from app.platform.identity.application.use_cases import IdentityUseCases
from app.platform.identity.infrastructure.unit_of_work import SqlIdentityUnitOfWork
from app.platform.identity.presentation.http.routers import CookieSettings, build_router
from app.shared.application.permissions import PermissionRegistry
from app.shared.module import PlatformServices


def build_identity_use_cases(
    services: PlatformServices,
    *,
    hasher: PasswordHasher,
    tokens: AccessTokenIssuer,
    permissions: PermissionRegistry,
    directory: TenantDirectory,
    refresh_ttl: timedelta,
) -> IdentityUseCases:
    uow = SqlIdentityUnitOfWork(services.session_factory)
    clock, ids = services.clock, services.ids
    sessions = SessionIssuer(tokens, permissions, directory, clock, ids, refresh_ttl)
    return IdentityUseCases(
        login=Login(uow, hasher, sessions),
        refresh=RefreshUserSession(uow, sessions, clock),
        logout=Logout(uow, clock),
        change_password=ChangePassword(uow, hasher, clock),
        create_user=CreateUser(uow, hasher, clock, ids),
        get_me=GetMe(uow, directory),
        list_members=ListMembers(uow),
        add_member=AddMember(uow, hasher, clock, ids),
        change_member_role=ChangeMemberRole(uow, clock),
        remove_member=RemoveMember(uow, clock),
    )


def build_identity_router(use_cases: IdentityUseCases, *, secure_cookies: bool) -> APIRouter:
    return build_router(use_cases, CookieSettings(secure=secure_cookies))
