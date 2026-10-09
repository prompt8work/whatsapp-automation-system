"""Built-in roles a dashboard user can have in a tenant (PRD §5).

Roles never appear in `if` statements: code checks PERMISSIONS (`require("contact.read")`).
Which permissions a role grants is declared by each module (`ModuleDefinition.role_grants`).
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"  # tenant admin: every permission of every installed module
    STAFF = "staff"  # receptionist / front desk
    DOCTOR = "doctor"
