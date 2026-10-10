from __future__ import annotations

from app.platform.contacts.infrastructure.purge import ContactPurger
from app.platform.contacts.presentation.http.routers import HTTP_ERROR_STATUS
from app.platform.contacts.wiring import build_routers
from app.shared.kernel.roles import Role
from app.shared.module import ModuleDefinition, PlatformServices


def _purger(services: PlatformServices) -> ContactPurger:
    return ContactPurger(services.purge_session_factory, services.clock)


module = ModuleDefinition(
    key="contacts",
    build_routers=build_routers,
    http_error_status=HTTP_ERROR_STATUS,
    permissions={
        "contact.read": "See WhatsApp contacts and their phone numbers",
        "contact.manage": "Change a contact's reminder opt-out",
    },
    role_grants={
        Role.STAFF: {"contact.read", "contact.manage"},
        Role.DOCTOR: {"contact.read"},
    },
    purgers=[_purger],  # RT-4: unused contacts
)
