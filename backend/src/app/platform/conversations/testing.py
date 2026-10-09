"""Test harness for WhatsApp flows: the REAL pipeline, engine and router with in-memory fakes.

    chat = ConversationHarness(flows=[my_flow], rules=[MyRule()], locale_dirs=[MY_LOCALES],
                               modules={"mymodule"})
    assert await chat.send("hi") == ["Welcome! ..."]
    await chat.tap(1)                       # press the first button of the last message
    assert chat.contact.has_consent

No database, no network, milliseconds per conversation (ARCHITECTURE §12 "Flow" tests).
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from app.platform.conversations.application.engine import FlowEngine, FlowRegistry, Router
from app.platform.conversations.application.handle_inbound import HandleInboundMessage
from app.platform.conversations.domain.session import ConversationSession
from app.platform.conversations.infrastructure.translator import TomlTranslator
from app.platform.conversations.wiring import LOCALES
from app.platform.messaging.contracts import InboundKind, InboundMessage
from app.platform.tenancy.contracts import TenantRoute
from app.shared.application.conversation import ContactInfo, Flow, RouterRule
from app.shared.application.messaging import SendReceipt, SendRequest
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import Buttons, Choice, ListMenu, OutboundMessage
from app.shared.testing.fakes import FixedClock, InMemoryUnitOfWork, SequentialIds

TENANT = TenantId(UUID(int=0xC1))
PHONE_NUMBER_ID = "100000000000001"


class InMemorySessions:
    def __init__(self) -> None:
        self.rows: dict[UUID, ConversationSession] = {}

    async def lock_and_get(self, contact_id: UUID) -> ConversationSession | None:
        found = self.rows.get(contact_id)
        return copy.deepcopy(found) if found else None

    async def save(self, session: ConversationSession) -> None:
        self.rows[session.contact_id] = copy.deepcopy(session)


class InMemoryConversationsUoW(InMemoryUnitOfWork):
    def __init__(self, sessions: InMemorySessions) -> None:
        super().__init__()
        self.sessions = sessions

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


class FakeContacts:
    def __init__(self) -> None:
        self.contacts: dict[str, ContactInfo] = {}

    async def resolve(
        self, tenant_id: TenantId, wa_id: str, profile_name: str | None
    ) -> ContactInfo:
        existing = self.contacts.get(wa_id)
        if existing:
            self.contacts[wa_id] = replace(existing, is_new=False)
        else:
            self.contacts[wa_id] = ContactInfo(
                uuid4(), f"+{wa_id}", profile_name, False, False, is_new=True
            )
        return self.contacts[wa_id]

    def _wa_id(self, contact_id: UUID) -> str:
        return next(wa for wa, c in self.contacts.items() if c.id == contact_id)

    async def set_opt_out(self, tenant_id: TenantId, contact_id: UUID, opted_out: bool) -> None:
        wa_id = self._wa_id(contact_id)
        self.contacts[wa_id] = replace(self.contacts[wa_id], is_opted_out=opted_out)

    async def grant_consent(self, tenant_id: TenantId, contact_id: UUID) -> None:
        wa_id = self._wa_id(contact_id)
        self.contacts[wa_id] = replace(self.contacts[wa_id], has_consent=True)


class RecordingMessenger:
    def __init__(self) -> None:
        self.sent: list[SendRequest] = []

    async def send(self, request: SendRequest) -> SendReceipt:
        self.sent.append(request)
        return SendReceipt(uuid4(), sent=True)


class FakeHandover:
    def __init__(self) -> None:
        self.active: set[UUID] = set()
        self.requests: list[UUID] = []

    async def is_active(self, tenant_id: TenantId, contact_id: UUID) -> bool:
        return contact_id in self.active

    async def request(self, tenant_id: TenantId, contact_id: UUID, reason: str) -> None:
        self.requests.append(contact_id)


class ConversationHarness:
    def __init__(
        self,
        *,
        flows: Iterable[Flow] = (),
        rules: Iterable[RouterRule] = (),
        locale_dirs: Iterable[Path] = (),
        modules: Iterable[str] = (),
        wa_id: str = "919800000001",
        clock: FixedClock | None = None,
    ) -> None:
        self.clock = clock or FixedClock()
        self.wa_id = wa_id
        self.sessions = InMemorySessions()
        self.contacts = FakeContacts()
        self.messenger = RecordingMessenger()
        self.handover = FakeHandover()
        self._flows = FlowRegistry()
        for flow in flows:
            self._flows.register(flow)
        self.translator = TomlTranslator([LOCALES, *locale_dirs])
        self.route = TenantRoute(TENANT, uuid4(), "Asia/Kolkata", frozenset(modules))
        self._pipeline = HandleInboundMessage(
            lambda _tenant: InMemoryConversationsUoW(self.sessions),
            FlowEngine(self._flows),
            Router(list(rules)),
            self.contacts,
            self.messenger,
            self.handover,
            self.translator,
            self.clock,
            SequentialIds(),
        )

    def add_flow(self, flow: Flow) -> None:
        """For flows whose steps need the harness's fakes (e.g. AskConsent(chat.contacts))."""
        self._flows.register(flow)

    @property
    def contact(self) -> ContactInfo:
        return self.contacts.contacts[self.wa_id]

    @property
    def session(self) -> ConversationSession | None:
        return (
            self.sessions.rows.get(self.contact.id)
            if self.wa_id in self.contacts.contacts
            else None
        )

    @property
    def last_message(self) -> OutboundMessage:
        return self.messenger.sent[-1].message

    async def send(
        self, text: str, *, choice_id: str | None = None, kind: InboundKind | None = None
    ) -> list[str]:
        """Send one message as the contact; returns the bot's replies as plain text."""
        already = len(self.messenger.sent)
        contact = await self.contacts.resolve(TENANT, self.wa_id, "Test Patient")
        message = InboundMessage(
            phone_number_id=PHONE_NUMBER_ID,
            wa_message_id=f"wamid.{uuid4().hex}",
            wa_id=self.wa_id,
            profile_name="Test Patient",
            sent_at=datetime.now(self.clock.now().tzinfo),
            kind=kind or (InboundKind.CHOICE if choice_id else InboundKind.TEXT),
            text=text,
            choice_id=choice_id,
        )
        await self._pipeline(self.route, contact, message)
        return [s.message.as_text() for s in self.messenger.sent[already:]]

    async def tap(self, number: int) -> list[str]:
        """Press button/list row `number` (1-based) of the bot's last message."""
        message = self.last_message
        if not isinstance(message, Buttons | ListMenu):
            raise AssertionError(f"Last message has no buttons: {message.as_text()!r}")
        choice: Choice = message.choices[number - 1]
        return await self.send(choice.title, choice_id=choice.id)
