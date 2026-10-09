"""Domain errors.

Every business-rule violation is a `DomainError` subclass with a stable `code`.
The presentation layer maps codes to HTTP statuses (shared/presentation/errors.py)
or to bot messages (locales). Codes are part of the API contract - never rename one.
"""

from __future__ import annotations


class DomainError(Exception):
    code: str = "domain.error"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.code
        super().__init__(self.message)


class NotFoundError(DomainError):
    code = "not_found"


class ConcurrencyConflictError(DomainError):
    """Optimistic-lock failure: someone else changed the record first. Client should retry."""

    code = "concurrency.conflict"


class ValidationError(DomainError):
    code = "validation.failed"
