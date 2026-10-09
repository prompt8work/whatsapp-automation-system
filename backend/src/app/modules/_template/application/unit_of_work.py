"""This module's Unit of Work port: the shared one plus this module's repositories.

Repositories are read-only properties so any implementation (SQL, in-memory) fits.
"""

from __future__ import annotations

from typing import Protocol

from app.modules._template.domain.repositories import ItemRepository
from app.shared.application.unit_of_work import UnitOfWork


class TemplateUnitOfWork(UnitOfWork, Protocol):
    @property
    def items(self) -> ItemRepository: ...
