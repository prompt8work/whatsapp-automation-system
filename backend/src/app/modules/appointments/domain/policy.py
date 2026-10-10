"""A clinic's booking rules, built from its appointments module settings (PRD AP-7.7).

Defaults match the PRD: approval required, reason required, requests expire after 4 h,
patients cannot change within 2 h of the appointment, book at least 1 h ahead, up to 30 days.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from app.modules.appointments.domain.appointment import Appointment
from app.modules.appointments.domain.errors import (
    ChangeCutoffPassedError,
    InvalidBookingFieldsError,
    ReasonRequiredError,
)
from app.shared.kernel.actor import Actor, ActorKind


class FieldType(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    CHOICE = "choice"


@dataclass(frozen=True)
class BookingField:
    """A clinic-defined question asked at booking (PRD FR-1.3), e.g. age, "first visit?"."""

    key: str
    label: str
    type: FieldType = FieldType.TEXT
    required: bool = False
    options: tuple[str, ...] = ()

    def clean(self, value: Any) -> Any:
        text = str(value).strip()
        if self.type is FieldType.NUMBER:
            try:
                return float(text) if "." in text else int(text)
            except ValueError as exc:
                raise InvalidBookingFieldsError(f"{self.label}: enter a number") from exc
        if self.type is FieldType.DATE:
            try:
                return date.fromisoformat(text).isoformat()
            except ValueError as exc:
                raise InvalidBookingFieldsError(f"{self.label}: use YYYY-MM-DD") from exc
        if self.type is FieldType.CHOICE:
            match = next((o for o in self.options if o.lower() == text.lower()), None)
            if match is None:
                raise InvalidBookingFieldsError(
                    f"{self.label}: choose one of {', '.join(self.options)}"
                )
            return match
        if len(text) > 300:
            raise InvalidBookingFieldsError(f"{self.label}: at most 300 characters")
        return text


@dataclass(frozen=True)
class BookingPolicy:
    approval_required: bool = True
    reason_required: bool = True
    request_expiry: timedelta = timedelta(hours=4)
    change_cutoff: timedelta = timedelta(hours=2)
    min_notice: timedelta = timedelta(hours=1)
    horizon_days: int = 30
    booking_fields: tuple[BookingField, ...] = field(default=())

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> BookingPolicy:
        d = cls()
        return cls(
            approval_required=bool(settings.get("approval_required", d.approval_required)),
            reason_required=bool(settings.get("reason_required", d.reason_required)),
            request_expiry=timedelta(hours=float(settings.get("request_expiry_hours", 4))),
            change_cutoff=timedelta(hours=float(settings.get("change_cutoff_hours", 2))),
            min_notice=timedelta(minutes=float(settings.get("min_notice_minutes", 60))),
            horizon_days=int(settings.get("horizon_days", d.horizon_days)),
            booking_fields=tuple(
                BookingField(
                    key=f["key"],
                    label=f.get("label", f["key"]),
                    type=FieldType(f.get("type", "text")),
                    required=bool(f.get("required", False)),
                    options=tuple(f.get("options", ())),
                )
                for f in settings.get("booking_fields", ())
            ),
        )

    def clean_reason(self, reason: str | None) -> str:
        cleaned = " ".join((reason or "").split())[:500]
        if self.reason_required and not cleaned:
            raise ReasonRequiredError("Please tell us the reason for the visit")
        return cleaned

    def clean_fields(self, values: dict[str, Any]) -> dict[str, Any]:
        """Keep only the clinic's fields, typed; complain about missing required ones."""
        cleaned: dict[str, Any] = {}
        for f in self.booking_fields:
            raw = values.get(f.key)
            if raw is None or str(raw).strip() == "":
                if f.required:
                    raise InvalidBookingFieldsError(f"{f.label} is required")
                continue
            cleaned[f.key] = f.clean(raw)
        return cleaned

    def ensure_can_change(self, appointment: Appointment, actor: Actor, now: datetime) -> None:
        """Patients cannot reschedule/cancel inside the cut-off (AP-4.8); staff always can."""
        if actor.kind is ActorKind.STAFF:
            return
        if now >= appointment.slot.start - self.change_cutoff:
            raise ChangeCutoffPassedError("It's too close to the appointment to change it here")
