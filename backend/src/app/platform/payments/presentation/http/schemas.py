from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.platform.payments.application.dto import PaymentDTO

Method = Literal["whatsapp_pay", "razorpay_link", "at_clinic"]
Status = Literal["pending", "paid", "failed", "expired", "refunded"]


class PaymentResponse(BaseModel):
    id: UUID
    receipt_number: str
    subject_type: str | None
    subject_id: UUID | None
    payer_name: str
    payer_phone: str
    purpose: str
    amount_minor: int
    currency: str
    method: Method
    status: Status
    created_at: datetime
    expires_at: datetime | None
    pay_url: str | None
    transaction_id: str | None
    paid_at: datetime | None
    refunded_at: datetime | None
    note: str

    @classmethod
    def from_dto(cls, p: PaymentDTO) -> PaymentResponse:
        return cls.model_validate(p, from_attributes=True)


class NoteRequest(BaseModel):
    note: str = Field(default="", max_length=200)


class PaymentSettingsSchema(BaseModel):
    methods: list[Method] = Field(default_factory=list)
    whatsapp_pay_configuration: str = Field(default="", max_length=100)
    razorpay_key_id: str = Field(default="", max_length=64)


class PaymentSettingsResponse(PaymentSettingsSchema):
    razorpay_secrets_saved: bool
    razorpay_webhook_path: str  # where to point the Razorpay webhook


class RazorpaySecretsRequest(BaseModel):
    key_secret: str = Field(min_length=8, max_length=128)
    webhook_secret: str = Field(min_length=8, max_length=128)
