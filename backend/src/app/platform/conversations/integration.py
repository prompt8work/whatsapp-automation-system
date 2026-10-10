"""Wiring-level surface of conversations for other modules' wiring layers."""

from __future__ import annotations

from app.platform.conversations.application.steps import AskConsent
from app.platform.conversations.infrastructure.translator import TomlTranslator
from app.platform.conversations.wiring import ContactsAdapter
from app.shared.module import PlatformServices

__all__ = ["TomlTranslator", "consent_step"]


def consent_step(services: PlatformServices) -> AskConsent:
    return AskConsent(ContactsAdapter(services))
