"""Module plug-in contract (ARCHITECTURE §8.1, PRD goal G6).

Every module - platform or feature - exposes ONE `ModuleDefinition` in its `module.py`.
Bootstrap collects them: permissions go to the PermissionRegistry, job/event handlers to the
background runners, routers into the FastAPI app. The platform never imports a feature module
by name; feature modules are listed only in app/bootstrap/modules.py.

Fields are added as the platform parts they plug into are built (purgers come with retention
in build step 7).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.application.audit import AuditLogger
from app.shared.application.conversation import Flow, RouterRule
from app.shared.application.events import EventHandler
from app.shared.application.jobs import JobHandler, JobScheduler
from app.shared.application.messaging import Messenger
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import IdGenerator
from app.shared.kernel.roles import Role


class PlatformServices(Protocol):
    """What the platform hands to a module when wiring it. Implemented by bootstrap.Container."""

    @property
    def clock(self) -> Clock: ...

    @property
    def ids(self) -> IdGenerator: ...

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]: ...

    @property
    def audit(self) -> AuditLogger: ...

    @property
    def jobs(self) -> JobScheduler: ...

    @property
    def messenger(self) -> Messenger: ...


JobHandlerFactory = Callable[[PlatformServices], JobHandler]
EventHandlerFactory = Callable[[PlatformServices], EventHandler]
FlowFactory = Callable[[PlatformServices], Flow]
RouterRuleFactory = Callable[[PlatformServices], RouterRule]


def _no_routers(_: PlatformServices) -> Sequence[APIRouter]:
    return ()


@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    build_routers: Callable[[PlatformServices], Sequence[APIRouter]] = _no_routers
    # DomainError.code -> HTTP status, for codes this module defines.
    http_error_status: Mapping[str, int] = field(default_factory=dict)
    # Permission key -> human description (shown in the dashboard's role editor later).
    permissions: Mapping[str, str] = field(default_factory=dict)
    # Which of THIS module's permissions each role gets. ADMIN gets all automatically.
    role_grants: Mapping[Role, Iterable[str]] = field(default_factory=dict)
    # job_type -> factory. job_type is prefixed with the module key: "appointments.send_reminder".
    job_handlers: Mapping[str, JobHandlerFactory] = field(default_factory=dict)
    # DomainEvent class name -> handler factories.
    event_handlers: Mapping[str, Sequence[EventHandlerFactory]] = field(default_factory=dict)
    # WhatsApp conversations (ARCHITECTURE §7): flows, the rules that start them, and the
    # folder with this module's bot sentences (<lang>.toml).
    flows: Sequence[FlowFactory] = ()
    router_rules: Sequence[RouterRuleFactory] = ()
    locales_dir: Path | None = None
