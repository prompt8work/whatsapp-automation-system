"""Everything this module plugs into the platform (ARCHITECTURE §8.1).

Install a module by adding its `module` to app/bootstrap/modules.py.
"""

from __future__ import annotations

from pathlib import Path

from app.modules._template.presentation.http.routers import HTTP_ERROR_STATUS
from app.modules._template.presentation.whatsapp.rules import NewItemKeywordRule
from app.modules._template.wiring import build_routers, create_item_flow
from app.shared.kernel.roles import Role
from app.shared.module import ModuleDefinition

module = ModuleDefinition(
    key="_template",
    build_routers=build_routers,
    http_error_status=HTTP_ERROR_STATUS,
    # Every route checks one of these (require(...) in routers.py). Admin gets all automatically.
    permissions={
        "template.item.read": "See items",
        "template.item.write": "Create and rename items",
    },
    role_grants={Role.STAFF: {"template.item.read", "template.item.write"}},
    # WhatsApp: the rule that starts the flow, the flow itself, and the bot sentences.
    router_rules=[lambda _services: NewItemKeywordRule()],
    flows=[create_item_flow],
    locales_dir=Path(__file__).parent / "locales",
)
