from __future__ import annotations

from app.shared.kernel.errors import DomainError, NotFoundError


class TenantNotFoundError(NotFoundError):
    code = "tenancy.tenant_not_found"


class LocationNotFoundError(NotFoundError):
    code = "tenancy.location_not_found"


class InvalidSlugError(DomainError):
    code = "tenancy.invalid_slug"


class SlugTakenError(DomainError):
    code = "tenancy.slug_taken"


class InvalidTimezoneError(DomainError):
    code = "tenancy.invalid_timezone"


class InvalidNameError(DomainError):
    code = "tenancy.invalid_name"


class ModuleNotEnabledError(DomainError):
    code = "tenancy.module_not_enabled"


class InvalidPhoneNumberIdError(DomainError):
    code = "tenancy.invalid_phone_number_id"


class PhoneNumberIdTakenError(DomainError):
    code = "tenancy.phone_number_id_taken"
