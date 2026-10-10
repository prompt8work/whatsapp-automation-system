"""Flow engine + pipeline, driven through the ConversationHarness (real code, fake I/O)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from app.platform.conversations.application.steps import AskConsent
from app.platform.conversations.testing import ConversationHarness
from app.platform.messaging.contracts import InboundKind
from app.shared.application.conversation import (
    BaseStep,
    Finish,
    Flow,
    FlowContext,
    InboundReply,
    Next,
    Retry,
    StartFlow,
    StepResult,
)

LOCALES = Path(__file__).parent / "locales"


class AskName(BaseStep):
    key = "name"

    async def should_skip(self, ctx: FlowContext) -> bool:
        return "name" in ctx.data

    async def prompt(self, ctx: FlowContext) -> None:
        ctx.say("What is your name?")

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        if not reply.text.isalpha():
            return Retry("demo.letters_only")
        ctx.data["name"] = reply.text
        return Next()


class AskColour(BaseStep):
    key = "colour"

    async def prompt(self, ctx: FlowContext) -> None:
        ctx.say("Favourite colour?")

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        if reply.normalized == "switch":
            return StartFlow("demo.other")
        ctx.say(f"Thanks {ctx.data['name']}, {reply.text} it is.")
        return Finish()


class Bye(BaseStep):
    key = "bye"

    async def prompt(self, ctx: FlowContext) -> None:
        ctx.say("Other flow here.")

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        return Finish()


class HelloRule:
    module_key = "demo"
    priority = 10

    async def flow_for(self, ctx: FlowContext) -> str | None:
        return "demo.survey" if ctx.reply.normalized in {"hi", "hello"} else None


def harness(*, modules: set[str] | None = None, consent: bool = False) -> ConversationHarness:
    chat = ConversationHarness(
        rules=[HelloRule()],
        locale_dirs=[LOCALES],
        modules={"demo"} if modules is None else modules,
    )
    first = (AskConsent(chat.contacts),) if consent else ()
    chat.add_flow(Flow("demo.survey", "demo", (*first, AskName(), AskColour())))
    chat.add_flow(Flow("demo.other", "demo", (Bye(),)))
    return chat


async def test_happy_path_runs_steps_in_order_and_finishes() -> None:
    chat = harness()
    assert await chat.send("hi") == ["What is your name?"]
    assert await chat.send("Rahul") == ["Favourite colour?"]
    assert await chat.send("Blue") == ["Thanks Rahul, Blue it is."]
    assert chat.session is not None
    assert chat.session.flow_key is None  # finished


async def test_unmatched_message_gets_the_platform_fallback() -> None:
    chat = harness()
    [reply] = await chat.send("what are your opening hours?")
    assert "Someone from our team will reply" in reply


async def test_rules_of_disabled_modules_are_ignored() -> None:
    chat = harness(modules=set())
    [reply] = await chat.send("hi")
    assert "Someone from our team will reply" in reply


async def test_retry_repeats_the_question_then_hands_over_after_three_failures() -> None:
    chat = harness()
    await chat.send("hi")
    assert await chat.send("R2D2") == ["Letters only, please.", "What is your name?"]
    await chat.send("C3PO")
    [final] = await chat.send("K2SO")

    assert "asked our team" in final
    assert chat.handover.requests == [chat.contact.id]
    assert chat.session is not None
    assert chat.session.flow_key is None


async def test_start_flow_jumps_to_another_flow() -> None:
    chat = harness()
    await chat.send("hi")
    await chat.send("Rahul")
    assert await chat.send("switch") == ["Other flow here."]
    assert chat.session is not None
    assert chat.session.flow_key == "demo.other"


async def test_unsupported_media_gets_a_hint_and_the_same_question() -> None:
    chat = harness()
    await chat.send("hi")
    replies = await chat.send("", kind=InboundKind.UNSUPPORTED)
    assert replies[-1] == "What is your name?"
    assert "only read text" in replies[0]


async def test_session_expires_after_24h_and_conversation_restarts() -> None:
    chat = harness()
    await chat.send("hi")
    chat.clock.advance(timedelta(hours=25))
    [reply] = await chat.send("Rahul")  # not a greeting, and the old flow expired
    assert "Someone from our team will reply" in reply


@pytest.mark.parametrize("word", ["STOP", "stop", " Stop "])
async def test_stop_opts_out_from_anywhere(word: str) -> None:
    chat = harness()
    await chat.send("hi")
    [reply] = await chat.send(word)
    assert "won't receive reminders" in reply
    assert chat.contact.is_opted_out
    [again] = await chat.send("START")
    assert "Welcome back" in again
    assert not chat.contact.is_opted_out


async def test_menu_abandons_the_flow_and_routes_again() -> None:
    chat = harness()
    await chat.send("hi")
    [reply] = await chat.send("menu")
    assert "Someone from our team will reply" in reply  # "menu" itself matches no rule here


async def test_agent_requests_a_human() -> None:
    chat = harness()
    [reply] = await chat.send("agent")
    assert "someone from our team" in reply.lower()
    assert chat.handover.requests == [chat.contact.id]


async def test_bot_is_silent_while_staff_handle_the_chat() -> None:
    chat = harness()
    await chat.send("hi")
    chat.handover.active.add(chat.contact.id)
    assert await chat.send("hello?") == []


async def test_consent_step_asks_once_and_is_skipped_afterwards() -> None:
    chat = harness(consent=True)
    [ask] = await chat.send("hi")
    assert "Is that okay?" in ask
    assert await chat.tap(1) == ["What is your name?"]
    assert chat.contact.has_consent

    await chat.send("Rahul")
    await chat.send("Blue")
    assert await chat.send("hi") == ["What is your name?"]  # consent not asked again


async def test_declining_consent_ends_the_flow() -> None:
    chat = harness(consent=True)
    await chat.send("hi")
    [reply] = await chat.tap(2)
    assert "change your mind" in reply
    assert not chat.contact.has_consent


async def test_flow_keyword_starts_its_flow_even_mid_flow() -> None:  # e.g. "DELETE MY DATA"
    chat = harness()
    chat.add_flow(Flow("demo.forget", "demo", (Bye(),), keywords=frozenset({"forget me"})))
    await chat.send("hi")
    assert await chat.send("Forget me!") == ["Other flow here."]
    assert chat.session is not None
    assert chat.session.flow_key == "demo.forget"


async def test_flow_keywords_of_disabled_modules_are_ignored() -> None:
    chat = harness(modules=set())
    chat.add_flow(Flow("demo.forget", "demo", (Bye(),), keywords=frozenset({"forget me"})))
    [reply] = await chat.send("forget me")
    assert "Someone from our team will reply" in reply
