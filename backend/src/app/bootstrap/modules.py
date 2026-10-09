"""Which modules make up the app.

PLATFORM_MODULES are always present. INSTALLED_MODULES are the feature plug-ins:
adding one = one line here (cookbook §11.7). `app.modules._template` is a copy-me example
and is deliberately NOT installed. The appointments module is added in build step 4.
"""

from __future__ import annotations

from app.platform.audit.module import module as audit
from app.platform.contacts.module import module as contacts
from app.platform.conversations.module import module as conversations
from app.platform.identity.module import module as identity
from app.platform.jobs.module import module as jobs
from app.platform.messaging.module import module as messaging
from app.platform.tenancy.module import module as tenancy
from app.shared.module import ModuleDefinition

PLATFORM_MODULES: list[ModuleDefinition] = [
    identity,
    tenancy,
    contacts,
    audit,
    jobs,
    messaging,
    conversations,
]

INSTALLED_MODULES: list[ModuleDefinition] = []
