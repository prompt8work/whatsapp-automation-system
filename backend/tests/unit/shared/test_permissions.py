from __future__ import annotations

import pytest

from app.bootstrap.modules import PLATFORM_MODULES
from app.shared.application.permissions import PermissionRegistry
from app.shared.kernel.roles import Role


def test_platform_modules_register_cleanly_and_grant_expected_permissions() -> None:
    registry = PermissionRegistry()
    for module in PLATFORM_MODULES:
        registry.register(module.permissions, module.role_grants)

    assert "users.manage" in registry.for_role(Role.ADMIN)
    assert "users.manage" not in registry.for_role(Role.STAFF)
    assert {"contact.read", "contact.manage"} <= registry.for_role(Role.STAFF)
    assert "contact.manage" not in registry.for_role(Role.DOCTOR)
    assert registry.for_role(None) == frozenset()


def test_duplicate_or_undeclared_permissions_fail_fast() -> None:
    registry = PermissionRegistry()
    registry.register({"a.read": ""}, {})
    with pytest.raises(ValueError, match="twice"):
        registry.register({"a.read": ""}, {})
    with pytest.raises(ValueError, match="undeclared"):
        registry.register({}, {Role.STAFF: {"b.read"}})
