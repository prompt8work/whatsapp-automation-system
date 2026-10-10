"""Wiring-level surface of retention for other modules' wiring layers (e.g. on-request
deletions write the same deletion record as the daily purge, AP-10.13)."""

from __future__ import annotations

from app.platform.retention.wiring import record_deletion_for

__all__ = ["record_deletion_for"]
