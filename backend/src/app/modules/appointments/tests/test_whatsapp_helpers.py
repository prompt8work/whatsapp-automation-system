"""Pure helpers of the WhatsApp layer + a guard that every bot text key exists."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from app.modules.appointments.presentation.whatsapp.formatting import when
from app.modules.appointments.presentation.whatsapp.parsing import parse_day, parse_time
from app.modules.appointments.wiring import LOCALES
from app.platform.conversations.integration import TomlTranslator
from app.platform.conversations.wiring import LOCALES as PLATFORM_LOCALES

TODAY = date(2026, 10, 12)  # a Monday


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("today", date(2026, 10, 12)),
        ("Tomorrow", date(2026, 10, 13)),
        ("kal", date(2026, 10, 13)),
        ("friday", date(2026, 10, 16)),
        ("next fri", date(2026, 10, 16)),
        ("monday", date(2026, 10, 12)),  # today counts
        ("16 oct", date(2026, 10, 16)),
        ("Oct 16th", date(2026, 10, 16)),
        ("16/10", date(2026, 10, 16)),
        ("16-10-2026", date(2026, 10, 16)),
        ("5 jan", date(2027, 1, 5)),  # already past this year -> next year
        ("31/02", None),
        ("someday", None),
    ],
)
def test_parse_day(text: str, expected: date | None) -> None:
    assert parse_day(text, TODAY) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3 pm", time(15)),
        ("3PM", time(15)),
        ("3:30 pm", time(15, 30)),
        ("15:00", time(15)),
        ("15.30", time(15, 30)),
        ("10am", time(10)),
        ("12 am", time(0)),
        ("noon", time(12)),
        ("3", time(15)),  # bare small hour at a clinic means afternoon
        ("25:00", None),
        ("soon", None),
    ],
)
def test_parse_time(text: str, expected: time | None) -> None:
    assert parse_time(text) == expected


def test_times_are_shown_in_the_clinic_timezone() -> None:
    assert when(datetime(2026, 10, 16, 9, 30, tzinfo=UTC), "Asia/Kolkata") == "Fri 16 Oct, 3:00 PM"


def test_every_bot_text_key_used_in_code_exists() -> None:
    texts = TomlTranslator([PLATFORM_LOCALES, LOCALES])
    source = "\n".join(
        p.read_text()
        for p in (Path(__file__).parents[1] / "presentation" / "whatsapp").glob("*.py")
    )
    keys = set(re.findall(r'"((?:appointments|conversations)\.[a-z_.]+)"', source))
    keys -= {
        "appointments.book",
        "appointments.menu",
        "appointments.reschedule",
        "appointments.cancel",
        "appointments.delete_data",
        "appointments.reminder_action",
        "appointments.reminder",
        "appointments.reminder_pay",
        "appointments.payment_due",
        "appointments.update",
        "appointments.send_reminder",  # job type
    }  # flow keys and template slots
    missing = sorted(k for k in keys if not texts.has(k))
    assert missing == []


def test_money_is_shown_the_indian_way() -> None:
    from app.modules.appointments.presentation.whatsapp.payments import money

    assert money(50000) == "₹500"
    assert money(123456789) == "₹12,34,567.89"
    assert money(100) == "₹1"
