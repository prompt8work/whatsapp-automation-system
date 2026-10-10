"""Retention wiring. Needs EVERY module's purgers, so bootstrap/platform.py calls
build_retention explicitly (like the jobs tick)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import APIRouter

from app.platform.retention.application.use_cases import (
    ListDeletionRecords,
    RecordDeletion,
    RunRetention,
    Upcoming,
)
from app.platform.retention.infrastructure.sql import SqlDeletionRecords
from app.platform.retention.presentation.http.routers import build_router
from app.platform.tenancy.integration import tenancy_for
from app.shared.module import ModuleDefinition, PlatformServices


def record_deletion_for(services: PlatformServices) -> RecordDeletion:
    return RecordDeletion(
        SqlDeletionRecords(services.session_factory), services.clock, services.ids
    )


@dataclass(frozen=True)
class Retention:
    run: RunRetention
    router: APIRouter


def build_retention(services: PlatformServices, modules: Sequence[ModuleDefinition]) -> Retention:
    # Feature modules first: deleting their records (patients) is what frees platform ones
    # (contacts) for their own purgers in the same run.
    purgers = [make(services) for module in reversed(modules) for make in module.purgers]
    records = SqlDeletionRecords(services.session_factory)
    return Retention(
        run=RunRetention(
            tenancy_for(services), purgers, record_deletion_for(services), services.clock
        ),
        router=build_router(ListDeletionRecords(records), Upcoming(purgers, services.clock)),
    )
