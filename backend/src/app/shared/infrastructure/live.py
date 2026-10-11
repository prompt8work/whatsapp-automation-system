"""Live topics (ARCHITECTURE §8.9): which dashboard areas a committed change affects.

Modules declare `live_topics` (DomainEvent class name -> topics) in their ModuleDefinition;
bootstrap registers them here once at startup. On commit, the Unit of Work bumps the version
of every affected topic for its tenant (`live_changes`), in the same transaction. Topics that
no event covers (e.g. a stored WhatsApp message) are touched explicitly: `uow.touch("inbox")`.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.infrastructure.tables import live_changes
from app.shared.kernel.ids import TenantId

_TOPICS: dict[str, set[str]] = {}


def register_live_topics(mapping: Mapping[str, Iterable[str]]) -> None:
    for event_type, topics in mapping.items():
        _TOPICS.setdefault(event_type, set()).update(topics)


def topics_for(event_types: Iterable[str]) -> set[str]:
    return {t for e in event_types for t in _TOPICS.get(e, ())}


async def bump(session: AsyncSession, tenant_id: TenantId, topics: Collection[str]) -> None:
    if not topics:
        return
    rows = [{"tenant_id": tenant_id, "topic": t, "version": 1} for t in sorted(topics)]
    stmt = insert(live_changes).values(rows)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["tenant_id", "topic"],
            set_={"version": live_changes.c.version + 1, "changed_at": func.now()},
        )
    )
