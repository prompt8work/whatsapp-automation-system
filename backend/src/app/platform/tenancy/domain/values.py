"""Small validation helpers shared by the tenancy aggregates."""

from __future__ import annotations

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.platform.tenancy.domain.errors import (
    InvalidNameError,
    InvalidSlugError,
    InvalidTimezoneError,
)

DEFAULT_TIMEZONE = "Asia/Kolkata"
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$")


def valid_name(name: str, *, max_length: int = 120) -> str:
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > max_length:
        raise InvalidNameError(f"Name must be 1-{max_length} characters")
    return cleaned


def valid_slug(slug: str) -> str:
    slug = slug.strip().lower()
    if not _SLUG.match(slug):
        raise InvalidSlugError("Use 3-40 lowercase letters, digits or hyphens, e.g. sunrise-clinic")
    return slug


def valid_timezone(tz: str) -> str:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidTimezoneError(f"Unknown timezone {tz!r}, e.g. Asia/Kolkata") from exc
    return tz
