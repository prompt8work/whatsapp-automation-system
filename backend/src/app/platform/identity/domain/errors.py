from __future__ import annotations

from app.shared.kernel.errors import DomainError, NotFoundError


class InvalidCredentialsError(DomainError):
    """Wrong email or password. Deliberately does not say which."""

    code = "identity.invalid_credentials"


class InvalidEmailError(DomainError):
    code = "identity.invalid_email"


class WeakPasswordError(DomainError):
    code = "identity.weak_password"


class EmailAlreadyUsedError(DomainError):
    code = "identity.email_taken"


class UserNotFoundError(NotFoundError):
    code = "identity.user_not_found"


class AlreadyMemberError(DomainError):
    code = "identity.already_member"


class NotAMemberError(DomainError):
    code = "identity.not_a_member"


class CannotChangeOwnMembershipError(DomainError):
    code = "identity.cannot_change_self"


class RefreshTokenInvalidError(DomainError):
    code = "identity.refresh_invalid"
