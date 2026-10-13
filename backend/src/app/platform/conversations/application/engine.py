"""Runs flows step by step (ARCHITECTURE §7.3). Knows nothing about any specific module.

start(flow)  -> begin session, prompt the first step that is not skipped
reply(...)   -> current step handles the answer -> Next / Retry / Finish / StartFlow
3 failed answers at one step -> apologise, ask a human to take over (PRD PL-5.3)
"""

from __future__ import annotations

import logging

from app.platform.conversations.domain.session import ConversationSession
from app.shared.application.conversation import (
    Finish,
    Flow,
    FlowContext,
    Next,
    Retry,
    RouterRule,
    StartFlow,
)
from app.shared.kernel.errors import DomainError

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


class FlowRegistry:
    def __init__(self) -> None:
        self._flows: dict[str, Flow] = {}

    def register(self, flow: Flow) -> None:
        if flow.key in self._flows:
            raise ValueError(f"Flow {flow.key!r} registered twice")
        if not flow.steps:
            raise ValueError(f"Flow {flow.key!r} has no steps")
        self._flows[flow.key] = flow

    def get(self, key: str) -> Flow | None:
        return self._flows.get(key)

    def for_reply(
        self, word: str, choice_id: str | None, enabled_modules: frozenset[str]
    ) -> Flow | None:
        """A flow that starts from anywhere on this keyword or tapped button."""
        return next(
            (
                f
                for f in self._flows.values()
                if f.module_key in enabled_modules and f.starts_on(word, choice_id)
            ),
            None,
        )


class Router:
    """Picks the flow for a new conversation: the first matching rule, in priority order,
    among rules of modules the tenant has enabled."""

    def __init__(self, rules: list[RouterRule]) -> None:
        self._rules = sorted(rules, key=lambda r: r.priority)

    async def flow_for(self, ctx: FlowContext) -> str | None:
        for rule in self._rules:
            if rule.module_key != "platform" and rule.module_key not in ctx.enabled_modules:
                continue
            flow_key = await rule.flow_for(ctx)
            if flow_key:
                return flow_key
        return None


class FlowEngine:
    def __init__(self, flows: FlowRegistry, *, max_attempts: int = MAX_ATTEMPTS) -> None:
        self._flows, self._max_attempts = flows, max_attempts

    def keyword_flow(self, ctx: FlowContext) -> str | None:
        flow = self._flows.for_reply(ctx.reply.normalized, ctx.reply.choice_id, ctx.enabled_modules)
        return flow.key if flow else None

    async def start(self, ctx: FlowContext, session: ConversationSession, flow_key: str) -> None:
        flow = self._flows.get(flow_key)
        if flow is None:
            raise KeyError(f"Unknown flow {flow_key!r}")
        session.begin(flow_key, ctx.now)
        ctx.data = session.data
        await self._enter(ctx, session, flow, 0)

    async def reply(self, ctx: FlowContext, session: ConversationSession) -> bool:
        """Continue the session's flow. False if the flow/step no longer exists (e.g. a
        deploy changed it) - the session is ended and the caller routes afresh."""
        flow = self._flows.get(session.flow_key or "")
        if flow is None or session.step_key is None:
            session.finish(ctx.now)
            return False
        try:
            index = flow.index_of(session.step_key)
        except KeyError:
            session.finish(ctx.now)
            return False
        step = flow.steps[index]
        ctx.data = session.data
        session.touch(ctx.now)

        if not ctx.reply.is_supported:
            ctx.say(ctx.t("conversations.unsupported"))
            await step.prompt(ctx)
            return True

        try:
            result = await step.handle(ctx, ctx.reply)
        except DomainError as exc:
            log.warning(
                "flow.step_error",
                extra={
                    "flow": flow.key,
                    "step": step.key,
                    "error": exc.code,
                    "detail": exc.message,
                },
            )
            result = Retry("conversations.try_again")

        match result:
            case Next(step_key=target):
                await self._enter(
                    ctx, session, flow, flow.index_of(target) if target else index + 1
                )
            case Retry(message_key=key, params=params):
                if session.failed_attempt() >= self._max_attempts:
                    ctx.say(ctx.t("conversations.too_many_attempts"))
                    ctx.request_handover()
                    session.finish(ctx.now)
                else:
                    ctx.say(ctx.t(key, **params))
                    await step.prompt(ctx)
            case Finish():
                session.finish(ctx.now)
            case StartFlow(flow_key=other):
                await self.start(ctx, session, other)
        return True

    async def reprompt(self, ctx: FlowContext, session: ConversationSession) -> bool:
        """Ask the current step's question again (R7 "Continue")."""
        flow = self._flows.get(session.flow_key or "")
        if flow is None or session.step_key is None:
            return False
        try:
            step = flow.steps[flow.index_of(session.step_key)]
        except KeyError:
            return False
        ctx.data = session.data
        session.touch(ctx.now)
        await step.prompt(ctx)
        return True

    async def _enter(
        self, ctx: FlowContext, session: ConversationSession, flow: Flow, index: int
    ) -> None:
        while index < len(flow.steps):
            step = flow.steps[index]
            if not await step.should_skip(ctx):
                session.at_step(step.key, ctx.now)
                await step.prompt(ctx)
                return
            index += 1
        session.finish(ctx.now)  # every remaining step was already answered
