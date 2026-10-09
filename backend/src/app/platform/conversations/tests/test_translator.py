from __future__ import annotations

from pathlib import Path

import pytest

from app.platform.conversations.infrastructure.translator import TomlTranslator
from app.platform.conversations.wiring import LOCALES


def write(tmp_path: Path, name: str, content: str) -> Path:
    folder = tmp_path / name
    folder.mkdir()
    (folder / "en.toml").write_text(content)
    return folder


def test_nested_tables_become_dotted_keys_and_params_are_filled(tmp_path: Path) -> None:
    folder = write(tmp_path, "m", '[shop.order]\ndone = "Order {ref} placed"\n')
    t = TomlTranslator([folder])
    assert t.t("shop.order.done", ref="A1") == "Order A1 placed"


def test_missing_key_returns_the_key_instead_of_crashing(tmp_path: Path) -> None:
    assert TomlTranslator([]).t("nope.missing") == "nope.missing"


def test_missing_param_returns_the_raw_template(tmp_path: Path) -> None:
    folder = write(tmp_path, "m", '[a]\nb = "Hi {name}"\n')
    assert TomlTranslator([folder]).t("a.b") == "Hi {name}"


def test_two_modules_defining_the_same_key_fail_at_startup(tmp_path: Path) -> None:
    one = write(tmp_path, "one", '[x]\ny = "1"\n')
    two = write(tmp_path, "two", '[x]\ny = "2"\n')
    with pytest.raises(ValueError, match="Duplicate"):
        TomlTranslator([one, two])


def test_platform_texts_load() -> None:
    t = TomlTranslator([LOCALES])
    assert t.has("conversations.fallback")
    assert t.has("conversations.consent.ask")
