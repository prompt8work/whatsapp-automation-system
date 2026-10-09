"""Permission catalogue built from every module's declarations (PRD PL-8.2).

Each module declares, in its ModuleDefinition:
    permissions = {"contact.read": "View contacts", ...}
    role_grants = {Role.STAFF: {"contact.read"}, Role.DOCTOR: {...}}
ADMIN automatically gets every declared permission.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from app.shared.kernel.roles import Role


class PermissionRegistry:
    def __init__(self) -> None:
        self._descriptions: dict[str, str] = {}
        self._grants: dict[Role, set[str]] = {role: set() for role in Role}

    def register(
        self,
        permissions: Mapping[str, str],
        role_grants: Mapping[Role, Iterable[str]],
    ) -> None:
        for key, description in permissions.items():
            if key in self._descriptions:
                raise ValueError(f"Permission {key!r} declared twice")
            self._descriptions[key] = description
        for role, keys in role_grants.items():
            unknown = set(keys) - self._descriptions.keys()
            if unknown:
                raise ValueError(f"Role {role} granted undeclared permissions {sorted(unknown)}")
            self._grants[role].update(keys)

    def for_role(self, role: Role | None) -> frozenset[str]:
        if role is None:
            return frozenset()
        if role is Role.ADMIN:
            return frozenset(self._descriptions)
        return frozenset(self._grants[role])

    @property
    def catalogue(self) -> Mapping[str, str]:
        return dict(self._descriptions)
