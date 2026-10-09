from __future__ import annotations

from app.shared.kernel.errors import DomainError, NotFoundError


class ContactNotFoundError(NotFoundError):
    code = "contacts.not_found"


class InvalidPhoneNumberError(DomainError):
    code = "contacts.invalid_phone"
