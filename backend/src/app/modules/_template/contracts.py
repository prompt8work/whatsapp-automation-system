"""Public surface of this module for OTHER modules (ARCHITECTURE §3.3).

Other modules may import ONLY this file (and listen to this module's domain events).
Expose small facades and DTOs here; never domain objects, repositories or tables.
"""

from __future__ import annotations

from app.modules._template.application.dto import ItemDTO

__all__ = ["ItemDTO"]
