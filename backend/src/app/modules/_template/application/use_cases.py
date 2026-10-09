"""All use cases of this module for ONE tenant, built per request by wiring.py.

Routers (and later WhatsApp flow steps) depend on this bundle, never on infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules._template.application.commands.create_item import CreateItem
from app.modules._template.application.commands.rename_item import RenameItem
from app.modules._template.application.queries.get_item import GetItem


@dataclass(frozen=True)
class ItemUseCases:
    create: CreateItem
    rename: RenameItem
    get: GetItem
