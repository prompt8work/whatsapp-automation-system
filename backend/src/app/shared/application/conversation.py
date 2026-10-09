"""The plug-in API for WhatsApp conversations (ARCHITECTURE §7). Modules write against this;
the engine that runs it lives in app/platform/conversations.

A module contributes:
- RouterRules: "when a conversation starts and <condition>, run flow X" (PRD §7.1, R1-R11)
- Flows: an ordered list of Steps. Each Step asks ONE question:
      prompt(ctx)        -> ctx.say(...) the question
      handle(ctx, reply) -> Next() / Retry("key") / Finish() / StartFlow("other.flow")
      should_skip(ctx)   -> True when the answer is already known (DR-5: never ask twice)
- Bot sentences in locales/<lang>.toml, used via ctx.t("module.key", name=...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import OutboundMessage, Text


class Translator(Protocol):
    def t(self, key: str, /, **params: Any) -> str: ...


@dataclass(frozen=True)
class ContactInfo:
    id: UUID
    phone: str  # E.164
    profile_name: str | None
    has_consent: bool
    is_opted_out: bool
    is_new: bool  # first message ever from this number (greeting rule R1)


@dataclass(frozen=True)
class InboundReply:
    text: str  # what the person typed, or the title of the button they tapped
    choice_id: str | None = None  # the Choice.id of a tapped button/list row
    is_supported: bool = True  # False for images, audio, stickers ...

    @property
    def normalized(self) -> str:
        return " ".join(self.text.lower().split())


@dataclass
class FlowContext:
    tenant_id: TenantId
    contact: ContactInfo
    reply: InboundReply
    data: dict[str, Any]  # answers collected so far in the current flow (saved in the session)
    translator: Translator
    now: datetime
    enabled_modules: frozenset[str]
    outbox: list[OutboundMessage] = field(default_factory=list)
    handover_requested: bool = False

    def t(self, key: str, /, **params: Any) -> str:
        return self.translator.t(key, **params)

    def say(self, message: OutboundMessage | str) -> None:
        self.outbox.append(Text(message) if isinstance(message, str) else message)

    def request_handover(self) -> None:
        """Ask a human to take over this conversation (PRD PL-5.3)."""
        self.handover_requested = True


# ------------------------------------------------------------------ step results
@dataclass(frozen=True)
class Next:
    """Go to the next step (or to `step_key`)."""

    step_key: str | None = None


@dataclass(frozen=True)
class Retry:
    """The reply was not usable: say `message_key` and ask the same question again."""

    message_key: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Finish:
    """The flow is complete."""


@dataclass(frozen=True)
class StartFlow:
    """Leave this flow and start another one (e.g. menu choice "Reschedule")."""

    flow_key: str


StepResult = Next | Retry | Finish | StartFlow


class Step(Protocol):
    key: str

    async def should_skip(self, ctx: FlowContext) -> bool: ...

    async def prompt(self, ctx: FlowContext) -> None: ...

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult: ...


class BaseStep:
    """Convenience base: never skipped. Subclasses set `key` and implement prompt/handle."""

    key: str = ""

    async def should_skip(self, ctx: FlowContext) -> bool:
        return False


@dataclass(frozen=True)
class Flow:
    key: str  # "<module>.<name>", e.g. "appointments.booking"
    module_key: str
    steps: tuple[Step, ...]

    def index_of(self, step_key: str) -> int:
        for i, step in enumerate(self.steps):
            if step.key == step_key:
                return i
        raise KeyError(f"{self.key} has no step {step_key!r}")


class RouterRule(Protocol):
    """Decides which flow starts a NEW conversation (no flow in progress)."""

    module_key: str
    priority: int  # lower runs first

    async def flow_for(self, ctx: FlowContext) -> str | None:
        """The flow key to start, or None if this rule does not apply."""
        ...
