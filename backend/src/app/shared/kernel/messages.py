"""What the bot wants to say - independent of any channel (ARCHITECTURE §7.3).

Flows build these; the WhatsApp adapter turns them into Meta JSON. Limits are WhatsApp's,
checked here so a flow fails in tests, not in production.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.shared.kernel.errors import DomainError

MAX_BODY = 1024  # interactive body text (plain text messages allow 4096)
MAX_TEXT = 4096
MAX_BUTTONS = 3
MAX_BUTTON_TITLE = 20
MAX_LIST_ROWS = 10
MAX_ROW_TITLE = 24
MAX_ROW_DESCRIPTION = 72


class InvalidMessageError(DomainError):
    code = "messaging.invalid_message"


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidMessageError(message)


@dataclass(frozen=True)
class Text:
    body: str

    def __post_init__(self) -> None:
        _check(0 < len(self.body) <= MAX_TEXT, f"Text must be 1-{MAX_TEXT} characters")

    def as_text(self) -> str:
        return self.body


@dataclass(frozen=True)
class Choice:
    id: str  # what comes back in the reply (e.g. "doctor:42")
    title: str
    description: str | None = None


@dataclass(frozen=True)
class Buttons:
    """Up to 3 reply buttons."""

    body: str
    choices: tuple[Choice, ...]

    def __post_init__(self) -> None:
        _check(0 < len(self.body) <= MAX_BODY, f"Body must be 1-{MAX_BODY} characters")
        _check(0 < len(self.choices) <= MAX_BUTTONS, f"1-{MAX_BUTTONS} buttons")
        for c in self.choices:
            _check(
                len(c.title) <= MAX_BUTTON_TITLE,
                f"Button title over {MAX_BUTTON_TITLE}: {c.title!r}",
            )

    def as_text(self) -> str:
        return _numbered(self.body, self.choices)


@dataclass(frozen=True)
class ListMenu:
    """A menu of up to 10 rows behind one button."""

    body: str
    button: str
    choices: tuple[Choice, ...]

    def __post_init__(self) -> None:
        _check(0 < len(self.body) <= MAX_BODY, f"Body must be 1-{MAX_BODY} characters")
        _check(len(self.button) <= MAX_BUTTON_TITLE, f"Button label over {MAX_BUTTON_TITLE}")
        _check(0 < len(self.choices) <= MAX_LIST_ROWS, f"1-{MAX_LIST_ROWS} rows")
        for c in self.choices:
            _check(len(c.title) <= MAX_ROW_TITLE, f"Row title over {MAX_ROW_TITLE}: {c.title!r}")
            _check(
                c.description is None or len(c.description) <= MAX_ROW_DESCRIPTION,
                f"Row description over {MAX_ROW_DESCRIPTION}",
            )

    def as_text(self) -> str:
        return _numbered(self.body, self.choices)


@dataclass(frozen=True)
class Template:
    """A Meta-approved template - the only kind allowed outside the 24 h window (PL-4.2)."""

    name: str
    language: str = "en"
    body_params: tuple[str, ...] = ()
    button_payloads: tuple[str, ...] = field(default=())  # quick-reply payloads, in order

    def as_text(self) -> str:
        return f"[template {self.name}] " + " | ".join(self.body_params)


OutboundMessage = Text | Buttons | ListMenu | Template


def menu(body: str, choices: list[Choice], *, button: str = "Choose") -> OutboundMessage:
    """Buttons when they fit (≤3 short titles), otherwise a list menu."""
    fits_buttons = len(choices) <= MAX_BUTTONS and all(
        len(c.title) <= MAX_BUTTON_TITLE for c in choices
    )
    return Buttons(body, tuple(choices)) if fits_buttons else ListMenu(body, button, tuple(choices))


def to_content(message: OutboundMessage) -> dict[str, Any]:
    """JSON form stored in the message log; `from_content` rebuilds it for a retry."""
    return {"kind": type(message).__name__, "text": message.as_text(), "payload": asdict(message)}


def from_content(content: dict[str, Any]) -> OutboundMessage:
    kind, p = content["kind"], content["payload"]
    if kind == "Text":
        return Text(p["body"])
    if kind == "Buttons":
        return Buttons(p["body"], tuple(Choice(**c) for c in p["choices"]))
    if kind == "ListMenu":
        return ListMenu(p["body"], p["button"], tuple(Choice(**c) for c in p["choices"]))
    if kind == "Template":
        return Template(
            p["name"], p["language"], tuple(p["body_params"]), tuple(p["button_payloads"])
        )
    raise InvalidMessageError(f"Unknown message kind {kind!r}")


def _numbered(body: str, choices: tuple[Choice, ...]) -> str:
    lines = [body, ""] + [f"{i}. {c.title}" for i, c in enumerate(choices, start=1)]
    return "\n".join(lines)
