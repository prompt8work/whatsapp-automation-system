"""Public types of conversations for other modules. Flows, steps and rules are written against
`app.shared.application.conversation`; ready-made steps that need platform services (e.g.
`consent_step`) are in `integration.py` for modules' wiring.
"""

from __future__ import annotations

from app.platform.conversations.application.steps import AskConsent

__all__ = ["AskConsent"]
