from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.platform.tenancy.application.dto import LocationDTO, TenantDTO, WhatsAppNumberDTO


class CreateTenantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=3, max_length=40, examples=["sunrise-clinic"])
    timezone: str = "Asia/Kolkata"
    modules: list[str] = Field(default_factory=list, examples=[["appointments"]])


class UpdateTenantRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    timezone: str | None = None


class TenantStatusRequest(BaseModel):
    status: Literal["active", "suspended"]


class TenantResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    timezone: str
    status: str
    modules: dict[str, dict[str, Any]]
    created_at: datetime

    @classmethod
    def from_dto(cls, t: TenantDTO) -> TenantResponse:
        return cls(
            id=t.id,
            name=t.name,
            slug=t.slug,
            timezone=t.timezone,
            status=t.status,
            modules=t.modules,
            created_at=t.created_at,
        )


class LocationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str = Field(default="", max_length=500)
    timezone: str | None = None


class UpdateLocationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=500)
    timezone: str | None = None
    is_active: bool | None = None


class LocationResponse(BaseModel):
    id: UUID
    name: str
    address: str
    timezone: str
    is_active: bool

    @classmethod
    def from_dto(cls, loc: LocationDTO) -> LocationResponse:
        return cls(
            id=loc.id,
            name=loc.name,
            address=loc.address,
            timezone=loc.timezone,
            is_active=loc.is_active,
        )


class ConnectNumberRequest(BaseModel):
    phone_number_id: str = Field(min_length=1, max_length=32, examples=["109876543210987"])
    display_phone: str = Field(min_length=1, max_length=32, examples=["+91 98765 43210"])


class WhatsAppNumberResponse(BaseModel):
    id: UUID
    phone_number_id: str
    display_phone: str
    is_active: bool

    @classmethod
    def from_dto(cls, n: WhatsAppNumberDTO) -> WhatsAppNumberResponse:
        return cls(
            id=n.id,
            phone_number_id=n.phone_number_id,
            display_phone=n.display_phone,
            is_active=n.is_active,
        )
