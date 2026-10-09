"""Row <-> domain conversion. The ONLY place that knows both shapes."""

from __future__ import annotations

from typing import Any

from sqlalchemy import RowMapping

from app.modules._template.domain.item import Item
from app.shared.kernel.ids import TenantId


def item_from_row(row: RowMapping) -> Item:
    return Item(
        id=row["id"],
        tenant_id=TenantId(row["tenant_id"]),
        name=row["name"],
        created_at=row["created_at"],
        version=row["version"],
    )


def item_to_row(item: Item) -> dict[str, Any]:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "name": item.name,
        "created_at": item.created_at,
        "version": item.version,
    }
