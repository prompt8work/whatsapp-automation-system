"""Phone numbers are always stored in E.164 form: "+919876543210" (PRD FR-2.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.platform.contacts.domain.errors import InvalidPhoneNumberError

_SEPARATORS = re.compile(r"[\s\-().]")


@dataclass(frozen=True)
class PhoneNumber:
    e164: str

    @classmethod
    def parse(cls, raw: str, *, default_country_code: str = "91") -> PhoneNumber:
        """Accepts "+91 98765-43210", "0091…", WhatsApp's wa_id "919876543210", or a
        national number "9876543210" / "09876543210" (the default country code is added)."""
        value = _SEPARATORS.sub("", raw)
        if value.startswith("00"):
            value = "+" + value[2:]
        if value.startswith("+"):
            digits = value[1:]
        elif value.startswith("0"):  # national with trunk prefix: 09876543210
            national = value[1:]
            digits = default_country_code + national if len(national) == 10 else "0"
        elif len(value) == 10:
            digits = default_country_code + value
        else:
            digits = value
        if not digits.isdigit() or not 8 <= len(digits) <= 15 or digits.startswith("0"):
            raise InvalidPhoneNumberError("Not a valid international phone number")
        return cls("+" + digits)

    def masked(self) -> str:
        """For places that must not show the full number: "+91•••••43210"."""
        return self.e164[:3] + "•" * (len(self.e164) - 8) + self.e164[-5:]

    def __str__(self) -> str:
        return self.e164
