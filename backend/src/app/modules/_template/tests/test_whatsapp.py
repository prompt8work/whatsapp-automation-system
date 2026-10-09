"""Flow test: a whole WhatsApp conversation through the module's real rule, steps and use cases,
with in-memory fakes. Copy this pattern for every flow (cookbook §11.3)."""

from __future__ import annotations

from pathlib import Path

from app.modules._template.application.commands.create_item import CreateItem
from app.modules._template.application.commands.rename_item import RenameItem
from app.modules._template.application.queries.get_item import GetItem
from app.modules._template.application.use_cases import ItemUseCases
from app.modules._template.presentation.whatsapp.rules import NewItemKeywordRule
from app.modules._template.presentation.whatsapp.steps import AskItemName
from app.modules._template.tests.fakes import InMemoryTemplateUnitOfWork
from app.platform.conversations.contracts import AskConsent
from app.platform.conversations.testing import ConversationHarness
from app.shared.application.conversation import Flow
from app.shared.kernel.ids import TenantId
from app.shared.testing.fakes import FixedClock, SequentialIds

LOCALES = Path(__file__).parents[1] / "locales"


def build() -> tuple[ConversationHarness, InMemoryTemplateUnitOfWork]:
    uow = InMemoryTemplateUnitOfWork()
    chat = ConversationHarness(
        rules=[NewItemKeywordRule()], locale_dirs=[LOCALES], modules={"_template"}
    )

    def use_cases_for(tenant_id: TenantId) -> ItemUseCases:
        clock = FixedClock()
        return ItemUseCases(
            create=CreateItem(uow, clock, SequentialIds(), tenant_id),
            rename=RenameItem(uow, clock),
            get=GetItem(uow),
        )

    chat.add_flow(
        Flow(
            "_template.create_item",
            "_template",
            (AskConsent(chat.contacts), AskItemName(use_cases_for)),
        )
    )
    return chat, uow


async def test_new_contact_creates_an_item_over_whatsapp() -> None:
    chat, uow = build()

    [consent] = await chat.send("item")
    assert "Is that okay?" in consent
    assert await chat.tap(1) == ["What should the new item be called?"]
    assert await chat.send("   ") == [
        "Please send a name between 1 and 100 characters.",
        "What should the new item be called?",
    ]
    assert await chat.send("Blue widget") == ['Done! I created "Blue widget".']

    [item] = uow.items.rows.values()
    assert item.name == "Blue widget"


async def test_returning_contact_is_not_asked_for_consent_again() -> None:
    chat, _ = build()
    await chat.send("item")
    await chat.tap(1)
    await chat.send("First")

    assert await chat.send("new item") == ["What should the new item be called?"]
