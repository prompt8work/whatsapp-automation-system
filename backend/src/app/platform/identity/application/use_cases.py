from __future__ import annotations

from dataclasses import dataclass

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
from app.platform.identity.application.queries.get_me import GetMe
from app.platform.identity.application.queries.list_members import ListMembers


@dataclass(frozen=True)
class IdentityUseCases:
    login: Login
    refresh: RefreshUserSession
    logout: Logout
    change_password: ChangePassword
    create_user: CreateUser
    get_me: GetMe
    list_members: ListMembers
    add_member: AddMember
    change_member_role: ChangeMemberRole
    remove_member: RemoveMember
