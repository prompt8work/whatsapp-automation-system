"""Appointments tables - all tenant-owned (RLS). appointment_events is append-only."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.shared.infrastructure.tables import metadata

TS = DateTime(timezone=True)

doctors = Table(
    "doctors",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("location_id", Uuid, ForeignKey("locations.id"), nullable=False),
    Column("name", String(120), nullable=False),
    Column("specialty", String(80), nullable=False),
    Column("slot_minutes", Integer, nullable=False),
    Column("user_id", Uuid, nullable=True),
    Column("is_active", Boolean, nullable=False),
    Column("working_hours", JSONB, nullable=False),
    Column("time_off", JSONB, nullable=False),
    Column("created_at", TS, nullable=False),
    Column("version", Integer, nullable=False),
    Index("ix_doctors_tenant", "tenant_id"),
)

patients = Table(
    "patients",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("contact_id", Uuid, ForeignKey("contacts.id"), nullable=False),
    Column("full_name", String(120), nullable=False),
    Column("created_at", TS, nullable=False),
    Column("version", Integer, nullable=False),
    Index("ix_patients_contact", "contact_id"),
)

cases = Table(
    "cases",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("patient_id", Uuid, ForeignKey("patients.id"), nullable=False),
    Column("status", String(10), nullable=False),
    Column("opened_at", TS, nullable=False),
    Column("last_activity_at", TS, nullable=False),
    Column("closed_at", TS, nullable=True),
    Column("closing_note", Text, nullable=False),
    Column("legal_hold", Boolean, nullable=False),
    Column("version", Integer, nullable=False),
    # At most one OPEN case per patient (new bookings join it - AP-10.1).
    Index(
        "uq_cases_one_open_per_patient",
        "patient_id",
        unique=True,
        postgresql_where=text("status = 'open'"),
    ),
)

appointments = Table(
    "appointments",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("reference", String(12), nullable=False),
    Column("case_id", Uuid, ForeignKey("cases.id"), nullable=False),
    Column("patient_id", Uuid, ForeignKey("patients.id"), nullable=False),
    Column("contact_id", Uuid, nullable=False),
    Column("location_id", Uuid, nullable=False),
    Column("doctor_id", Uuid, ForeignKey("doctors.id"), nullable=False),
    Column("start_at", TS, nullable=False),
    Column("end_at", TS, nullable=False),
    Column("original_doctor_id", Uuid, nullable=False),
    Column("original_start_at", TS, nullable=False),
    Column("original_end_at", TS, nullable=False),
    Column("pending_doctor_id", Uuid, nullable=True),
    Column("pending_start_at", TS, nullable=True),
    Column("pending_end_at", TS, nullable=True),
    Column("pending_since", TS, nullable=True),
    Column("status", String(12), nullable=False),
    Column("reason", Text, nullable=False),
    Column("fields", JSONB, nullable=False),
    Column("created_at", TS, nullable=False),
    Column("version", Integer, nullable=False),
    UniqueConstraint("tenant_id", "reference", name="uq_appointments_reference"),
    Index("ix_appointments_doctor_start", "tenant_id", "doctor_id", "start_at"),
    Index("ix_appointments_start", "tenant_id", "start_at"),
    Index("ix_appointments_contact", "contact_id"),
    Index("ix_appointments_case", "case_id"),
)

appointment_events = Table(
    "appointment_events",
    metadata,
    Column("id", Uuid, primary_key=True),  # = DomainEvent.event_id
    Column("tenant_id", Uuid, nullable=False),
    Column(
        "appointment_id",
        Uuid,
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("event_type", String(60), nullable=False),
    Column("actor", String(60), nullable=False),
    Column("channel", String(20), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("occurred_at", TS, nullable=False),
    Index("ix_appointment_events_appointment", "appointment_id", "occurred_at"),
)

slot_reservations = Table(
    "slot_reservations",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column(
        "appointment_id",
        Uuid,
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("doctor_id", Uuid, nullable=False),
    Column("kind", String(12), nullable=False),
    Column("start_at", TS, nullable=False),
    Column("end_at", TS, nullable=False),
    Column("active", Boolean, nullable=False),
    Column("created_at", TS, nullable=False),
    Index(
        "ix_slot_reservations_active",
        "doctor_id",
        "start_at",
        postgresql_where=text("active"),
    ),
)
