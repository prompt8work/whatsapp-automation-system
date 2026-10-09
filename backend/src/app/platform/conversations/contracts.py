"""Public surface of conversations for feature modules.

Flows, steps and rules are written against `app.shared.application.conversation`. This file
adds ready-made steps that need platform services:

    flows=[lambda s: Flow("appointments.booking", "appointments",
                          (consent_step(s), AskName(...), ...))]
"""

from __future__ import annotations

from app.platform.conversations.application.steps import AskConsent
from app.platform.conversations.wiring import ContactsAdapter
from app.shared.module import PlatformServices

__all__ = ["AskConsent", "consent_step"]


def consent_step(services: PlatformServices) -> AskConsent:
    return AskConsent(ContactsAdapter(services))
