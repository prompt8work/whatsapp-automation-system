"""A clinic's choice of Meta-approved template for one TemplateSlot (PRD PL-4.2)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.shared.kernel.messages import InvalidMessageError

_NAME = re.compile(r"^[a-z0-9_]{1,512}$")  # Meta template names: lowercase, digits, underscores


@dataclass(frozen=True)
class TemplateMapping:
    slot: str
    name: str
    language: str = "en"

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise InvalidMessageError("Template names use lowercase letters, digits and _ only")
        if not re.match(r"^[a-z]{2,3}(_[A-Z]{2})?$", self.language):
            raise InvalidMessageError("Language codes look like en, hi or en_US")
