"""Bot sentences from TOML files (ADR-010). Every module has locales/<lang>.toml; nested tables
become dotted keys: [appointments.booking] ask_name = "..." -> "appointments.booking.ask_name".
"""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _flatten(prefix: str, table: dict[str, Any], out: dict[str, str]) -> None:
    for key, value in table.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            _flatten(full, value, out)
        else:
            out[full] = str(value)


class TomlTranslator:
    def __init__(self, locale_dirs: Iterable[Path], language: str = "en") -> None:
        self._texts: dict[str, str] = {}
        for directory in locale_dirs:
            path = directory / f"{language}.toml"
            if not path.exists():
                continue
            flat: dict[str, str] = {}
            _flatten("", tomllib.loads(path.read_text(encoding="utf-8")), flat)
            duplicates = flat.keys() & self._texts.keys()
            if duplicates:
                raise ValueError(f"Duplicate bot text keys in {path}: {sorted(duplicates)}")
            self._texts.update(flat)

    def t(self, key: str, /, **params: Any) -> str:
        template = self._texts.get(key)
        if template is None:
            log.warning("i18n.missing_key", extra={"key": key})
            return key
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            log.warning("i18n.bad_params", extra={"key": key})
            return template

    def has(self, key: str) -> bool:
        return key in self._texts
