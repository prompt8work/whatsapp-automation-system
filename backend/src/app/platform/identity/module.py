from __future__ import annotations

from app.platform.identity.presentation.http.routers import HTTP_ERROR_STATUS
from app.shared.module import ModuleDefinition

# Routers are built explicitly by bootstrap (see wiring.py); this declares the rest.
module = ModuleDefinition(
    key="identity",
    http_error_status=HTTP_ERROR_STATUS,
    permissions={
        "users.read": "See the clinic's dashboard users",
        "users.manage": "Add or remove dashboard users and change their roles",
    },
    role_grants={},  # admin only
)
