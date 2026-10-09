from __future__ import annotations

from app.platform.tenancy.presentation.http.routers import HTTP_ERROR_STATUS
from app.platform.tenancy.wiring import build_routers
from app.shared.kernel.roles import Role
from app.shared.module import ModuleDefinition

module = ModuleDefinition(
    key="tenancy",
    build_routers=build_routers,
    http_error_status=HTTP_ERROR_STATUS,
    permissions={
        "tenant.settings.manage": "Change clinic name, timezone and module settings",
        "locations.read": "See clinic locations",
        "locations.manage": "Add and edit clinic locations",
    },
    role_grants={
        Role.STAFF: {"locations.read"},
        Role.DOCTOR: {"locations.read"},
    },
)
