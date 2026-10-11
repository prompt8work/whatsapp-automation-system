from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter

from app.platform.live.application.stream import LiveStream
from app.platform.live.infrastructure.sql import SqlLiveVersions
from app.platform.live.presentation.http.routers import build_router
from app.shared.module import ModuleDefinition, PlatformServices


def _build_routers(services: PlatformServices) -> Sequence[APIRouter]:
    return [build_router(LiveStream(SqlLiveVersions(services.session_factory)))]


module = ModuleDefinition(key="live", build_routers=_build_routers)
