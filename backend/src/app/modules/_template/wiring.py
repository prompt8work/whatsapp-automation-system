"""Module-level composition: the only file in the module that picks concrete classes.

It turns the platform's services into this module's use cases, HTTP routers and WhatsApp
flows (a flow = the module's steps in order, with the platform's consent step first).
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
from app.modules._template.presentation.whatsapp.steps import AskItemName
from app.platform.conversations.contracts import consent_step
from app.shared.application.conversation import Flow
from app.shared.kernel.ids import TenantId
from app.shared.module import PlatformServices


def use_cases_for(services: PlatformServices, tenant_id: TenantId) -> ItemUseCases:
    """Used by the HTTP routers AND the WhatsApp steps - same use cases for both channels."""
    uow = SqlTemplateUnitOfWork(services.session_factory, tenant_id)
    return ItemUseCases(
        create=CreateItem(uow, services.clock, services.ids, tenant_id),
        rename=RenameItem(uow, services.clock),
        get=GetItem(uow),
    )


def build_routers(services: PlatformServices) -> Sequence[APIRouter]:
    return [build_router(lambda tenant_id: use_cases_for(services, tenant_id))]


def create_item_flow(services: PlatformServices) -> Flow:
    return Flow(
        key="_template.create_item",
        module_key="_template",
        steps=(
            consent_step(services),
            AskItemName(lambda tenant_id: use_cases_for(services, tenant_id)),
        ),
    )
