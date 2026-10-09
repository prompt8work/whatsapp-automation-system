"""Business-rule violations for this module. Codes are prefixed with the module key."""

from __future__ import annotations

from app.shared.kernel.errors import DomainError, NotFoundError


class ItemNotFoundError(NotFoundError):
    code = "template.item_not_found"


class InvalidItemNameError(DomainError):
    code = "template.invalid_name"


class ItemNameUnchangedError(DomainError):
    code = "template.name_unchanged"
