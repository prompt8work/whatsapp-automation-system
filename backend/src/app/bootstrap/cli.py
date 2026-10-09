"""Operator commands (run against the database in DATABASE_URL). Prefix each with
`uv run python -m app.bootstrap.cli`:

    create-superadmin --email you@example.com --name "You"
    create-tenant --name "Sunrise Clinic" --slug sunrise-clinic --module appointments
    add-member --tenant sunrise-clinic --email dr@x.com --name "Dr Amit" --role doctor
    connect-whatsapp --tenant sunrise-clinic --phone-number-id 1098... --display-phone "+91 ..."
    tick        # run due events/jobs once (local dev, instead of Vercel Cron)

Passwords are prompted (never pass them on the command line - shell history).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from datetime import timedelta

from app.bootstrap.container import Container, build_container
from app.bootstrap.modules import INSTALLED_MODULES, PLATFORM_MODULES
from app.bootstrap.settings import get_settings
from app.platform.identity.application.commands.create_user import CreateUserCommand
from app.platform.identity.application.commands.members import AddMemberCommand
from app.platform.identity.application.use_cases import IdentityUseCases
from app.platform.identity.wiring import build_identity_use_cases
from app.platform.jobs.application.dispatch_outbox import DispatchOutbox
from app.platform.jobs.application.run_due_jobs import RunDueJobs
from app.platform.jobs.infrastructure.unit_of_work import SqlJobsUnitOfWork
from app.platform.tenancy.application.commands.connect_whatsapp_number import (
    ConnectWhatsAppNumber,
    ConnectWhatsAppNumberCommand,
)
from app.platform.tenancy.application.commands.tenants import CreateTenant, CreateTenantCommand
from app.platform.tenancy.application.queries.tenants import ListTenants
from app.platform.tenancy.infrastructure.unit_of_work import SqlTenancyUnitOfWork
from app.platform.tenancy.wiring import build_facade
from app.shared.kernel.actor import Actor
from app.shared.kernel.errors import DomainError
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role

SYSTEM = Actor.system()


def _identity(c: Container) -> IdentityUseCases:
    return build_identity_use_cases(
        c,
        hasher=c.password_hasher,
        tokens=c.access_tokens,
        permissions=c.permissions,
        directory=build_facade(c),
        refresh_ttl=timedelta(days=c.settings.refresh_token_days),
    )


def _password(prompt: str = "Password (min 10 chars): ") -> str:
    first = getpass.getpass(prompt)
    if getpass.getpass("Repeat password: ") != first:
        sys.exit("Passwords do not match")
    return first


async def _tenant_id(c: Container, slug: str) -> TenantId:
    tenants = await ListTenants(SqlTenancyUnitOfWork(c.session_factory, None))()
    for tenant in tenants:
        if tenant.slug == slug:
            return tenant.id
    sys.exit(f"No tenant with slug {slug!r}")


async def run(args: argparse.Namespace, c: Container) -> None:
    if args.command == "create-superadmin":
        user_id = await _identity(c).create_user(
            CreateUserCommand(args.email, args.name, _password(), SYSTEM, is_super_admin=True)
        )
        print(f"Super-admin created: {user_id}")

    elif args.command == "create-tenant":
        uow = SqlTenancyUnitOfWork(c.session_factory, None)
        tenant = await CreateTenant(uow, c.clock, c.ids)(
            CreateTenantCommand(
                args.name, args.slug, SYSTEM, timezone=args.timezone, modules=tuple(args.module)
            )
        )
        print(f"Tenant created: {tenant.id} ({tenant.slug})")

    elif args.command == "add-member":
        tenant_id = await _tenant_id(c, args.tenant)
        password = _password("Initial password (ignored if the user exists): ")
        member = await _identity(c).add_member(
            AddMemberCommand(tenant_id, args.email, args.name, Role(args.role), SYSTEM, password)
        )
        print(f"{member.email} is now {member.role} of {args.tenant}")

    elif args.command == "connect-whatsapp":
        tenant_id = await _tenant_id(c, args.tenant)
        uow = SqlTenancyUnitOfWork(c.session_factory, None)
        number = await ConnectWhatsAppNumber(uow, c.clock, c.ids)(
            ConnectWhatsAppNumberCommand(
                tenant_id, args.phone_number_id, args.display_phone, SYSTEM
            )
        )
        print(f"Connected {number.display_phone} -> {args.tenant}")

    elif args.command == "tick":
        jobs_uow = SqlJobsUnitOfWork(c.session_factory)
        events = await DispatchOutbox(jobs_uow, c.event_handlers, c.clock)()
        jobs = await RunDueJobs(jobs_uow, c.job_handlers, c.clock)()
        print(f"events: {events}\njobs:   {jobs}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.bootstrap.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-superadmin")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)

    p = sub.add_parser("create-tenant")
    p.add_argument("--name", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--timezone", default="Asia/Kolkata")
    p.add_argument("--module", action="append", default=[], help="repeatable")

    p = sub.add_parser("add-member")
    p.add_argument("--tenant", required=True, help="tenant slug")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--role", required=True, choices=[r.value for r in Role])

    p = sub.add_parser("connect-whatsapp")
    p.add_argument("--tenant", required=True, help="tenant slug")
    p.add_argument("--phone-number-id", required=True)
    p.add_argument("--display-phone", required=True)

    sub.add_parser("tick")

    args = parser.parse_args()
    container = build_container(get_settings(), [*PLATFORM_MODULES, *INSTALLED_MODULES])

    async def _main() -> None:
        try:
            await run(args, container)
        except DomainError as exc:
            sys.exit(f"Error ({exc.code}): {exc.message}")
        finally:
            await container.engine.dispose()

    asyncio.run(_main())


if __name__ == "__main__":
    main()
