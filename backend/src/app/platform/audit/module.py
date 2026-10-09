from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter

from app.platform.audit.application.queries.list_entries import ListAuditEntries
from app.platform.audit.infrastructure.sql import SqlAuditReadModel
from app.platform.audit.presentation.http.routers import build_router
from app.shared.module import ModuleDefinition, PlatformServices


def _build_routers(services: PlatformServices) -> Sequence[APIRouter]:
    return [
        build_router(
            lambda tenant_id: ListAuditEntries(
                SqlAuditReadModel(services.session_factory, tenant_id)
            )
        )
    ]


module = ModuleDefinition(
    key="audit",
    build_routers=_build_routers,
    permissions={"audit.read": "See who viewed or changed personal data"},
    role_grants={},  # admin only
)
