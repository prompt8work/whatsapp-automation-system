"""Module-level composition: the only file in the module that picks concrete classes.

It turns the platform's services into this module's use cases and routers.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter

from app.modules._template.application.commands.create_item import CreateItem
from app.modules._template.application.commands.rename_item import RenameItem
from app.modules._template.application.queries.get_item import GetItem
from app.modules._template.application.use_cases import ItemUseCases
from app.modules._template.infrastructure.unit_of_work import SqlTemplateUnitOfWork
from app.modules._template.presentation.http.routers import build_router
from app.shared.kernel.ids import TenantId
from app.shared.module import PlatformServices


def build_routers(services: PlatformServices) -> Sequence[APIRouter]:
    def use_cases_for(tenant_id: TenantId) -> ItemUseCases:
        uow = SqlTemplateUnitOfWork(services.session_factory, tenant_id)
        return ItemUseCases(
            create=CreateItem(uow, services.clock, services.ids, tenant_id),
            rename=RenameItem(uow, services.clock),
            get=GetItem(uow),
        )

    return [build_router(use_cases_for)]
