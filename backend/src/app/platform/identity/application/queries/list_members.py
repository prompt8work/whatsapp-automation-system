from __future__ import annotations

from app.platform.identity.application.dto import MemberDTO
from app.platform.identity.application.unit_of_work import IdentityUnitOfWork
from app.shared.kernel.ids import TenantId


class ListMembers:
    def __init__(self, uow: IdentityUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, tenant_id: TenantId) -> list[MemberDTO]:
        async with self._uow as uow:
            users = await uow.users.list_members(tenant_id)
        return sorted(
            (MemberDTO.from_domain(u, tenant_id) for u in users), key=lambda m: m.full_name.lower()
        )
