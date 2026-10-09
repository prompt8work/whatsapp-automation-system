"""Identifiers.

Primary keys are UUIDv7 (time-ordered, so B-tree indexes stay compact) - ADR-011.
The domain never generates ids itself; it receives an `IdGenerator` so tests are deterministic.
"""

from __future__ import annotations

import os
import time
from typing import NewType, Protocol
from uuid import UUID

TenantId = NewType("TenantId", UUID)


def uuid7() -> UUID:
    """Return a RFC 9562 version-7 UUID (Python 3.12 has no `uuid.uuid7`)."""
    unix_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")  # 80 random bits
    value = (unix_ms & ((1 << 48) - 1)) << 80  # 48-bit timestamp
    value |= 0x7 << 76  # version 7
    value |= ((rand >> 62) & 0xFFF) << 64  # 12 bits rand_a
    value |= 0b10 << 62  # RFC 4122 variant
    value |= rand & ((1 << 62) - 1)  # 62 bits rand_b
    return UUID(int=value)


class IdGenerator(Protocol):
    def new_id(self) -> UUID: ...


class Uuid7Generator:
    def new_id(self) -> UUID:
        return uuid7()
