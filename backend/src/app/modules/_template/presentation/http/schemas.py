"""Request/response shapes of the HTTP API (Pydantic). They become the frontend's TS types."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules._template.application.dto import ItemDTO


class CreateItemRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RenameItemRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ItemResponse(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    version: int

    @classmethod
    def from_dto(cls, dto: ItemDTO) -> ItemResponse:
        return cls(id=dto.id, name=dto.name, created_at=dto.created_at, version=dto.version)
