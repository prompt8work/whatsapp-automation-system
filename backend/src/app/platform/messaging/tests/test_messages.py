from __future__ import annotations

from uuid import UUID

import pytest

from app.platform.messaging.domain.inbound import DeliveryStatus
from app.platform.messaging.domain.message import Message, MessageStatus
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import (
    Buttons,
    Choice,
    InvalidMessageError,
    ListMenu,
    Template,
    Text,
    from_content,
    menu,
    to_content,
)
from app.shared.testing.fakes import FixedClock


def test_whatsapp_limits_are_enforced_when_building_messages() -> None:
    with pytest.raises(InvalidMessageError):
        Buttons("Pick", tuple(Choice(str(i), f"B{i}") for i in range(4)))  # max 3 buttons
    with pytest.raises(InvalidMessageError):
        Buttons("Pick", (Choice("x", "A title that is far too long"),))  # max 20 chars
    with pytest.raises(InvalidMessageError):
        Text("")


def test_menu_uses_buttons_when_they_fit_otherwise_a_list() -> None:
    short = [Choice("a", "Yes"), Choice("b", "No")]
    long = [Choice(str(i), f"Dr. Doctor number {i}") for i in range(5)]
    assert isinstance(menu("Q?", short), Buttons)
    assert isinstance(menu("Q?", long), ListMenu)


@pytest.mark.parametrize(
    "message",
    [
        Text("Hello"),
        Buttons("Q?", (Choice("y", "Yes"), Choice("n", "No"))),
        ListMenu("Q?", "Doctors", (Choice("d1", "Dr. Amit", "General"),)),
        Template("reminder", "en", ("Rahul", "Fri 3 PM"), ("confirm",)),
    ],
)
def test_content_round_trip_rebuilds_the_same_message(message: object) -> None:
    assert from_content(to_content(message)) == message  # type: ignore[arg-type]


def test_buttons_fall_back_to_a_numbered_text() -> None:
    assert Buttons("Pick one", (Choice("a", "Yes"), Choice("b", "No"))).as_text() == (
        "Pick one\n\n1. Yes\n2. No"
    )


def test_delivery_status_never_moves_backwards() -> None:
    message = Message.outbound(
        id=UUID(int=1),
        tenant_id=TenantId(UUID(int=2)),
        contact_id=UUID(int=3),
        phone_number_id="1",
        content={},
        at=FixedClock().now(),
    )
    message.mark_sent("wamid.1")
    message.apply_delivery_status(DeliveryStatus.READ)
    message.apply_delivery_status(DeliveryStatus.DELIVERED)  # late receipt
    assert message.status is MessageStatus.READ
