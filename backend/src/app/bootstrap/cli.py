"""Operator commands (run against the database in DATABASE_URL). Prefix each with
`uv run python -m app.bootstrap.cli`:

    create-superadmin --email you@example.com --name "You"
    create-tenant --name "Sunrise Clinic" --slug sunrise-clinic --module appointments
    add-member --tenant sunrise-clinic --email dr@x.com --name "Dr Amit" --role doctor
    connect-whatsapp --tenant sunrise-clinic --phone-number-id 1098... --display-phone "+91 ..."
    set-credentials --phone-number-id 1098...        # Meta access token, prompted, stored encrypted
    simulate --tenant sunrise-clinic --from 919876543210   # chat with the bot in the terminal
    tick        # run due events/jobs once (local dev, instead of Vercel Cron)
    seed-demo [--reset]   # a demo clinic full of realistic data (local only; password prompted)

Passwords and tokens are prompted (never pass secrets on the command line - shell history).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from datetime import UTC, datetime
from uuid import uuid4

from app.bootstrap.demo import seed_demo
from app.bootstrap.platform import Platform, build_platform
from app.bootstrap.settings import get_settings
from app.platform.identity.application.commands.create_user import CreateUserCommand
from app.platform.identity.application.commands.members import AddMemberCommand
from app.platform.jobs.application.dispatch_outbox import DispatchOutbox
from app.platform.jobs.application.run_due_jobs import RunDueJobs
from app.platform.jobs.infrastructure.unit_of_work import SqlJobsUnitOfWork
from app.platform.messaging.application.commands.statuses import (
    SetCredentials,
    SetCredentialsCommand,
)
from app.platform.messaging.contracts import InboundKind, InboundMessage, WebhookBatch
from app.platform.messaging.infrastructure.recording import RecordingGateway
from app.platform.tenancy.application.commands.connect_whatsapp_number import (
    ConnectWhatsAppNumber,
    ConnectWhatsAppNumberCommand,
)
from app.platform.tenancy.application.commands.tenants import CreateTenant, CreateTenantCommand
from app.platform.tenancy.application.queries.tenants import ListTenants, ListWhatsAppNumbers
from app.platform.tenancy.infrastructure.unit_of_work import SqlTenancyUnitOfWork
from app.shared.kernel.actor import Actor
from app.shared.kernel.errors import DomainError
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import Buttons, Choice, ListMenu, OutboundMessage
from app.shared.kernel.roles import Role

SYSTEM = Actor.system()


def _secret(prompt: str, *, confirm: bool = True) -> str:
    first = getpass.getpass(prompt)
    if confirm and getpass.getpass("Repeat: ") != first:
        sys.exit("Values do not match")
    return first


async def _tenant_id(p: Platform, slug: str) -> TenantId:
    tenants = await ListTenants(SqlTenancyUnitOfWork(p.container.session_factory, None))()
    for tenant in tenants:
        if tenant.slug == slug:
            return tenant.id
    sys.exit(f"No tenant with slug {slug!r}")


async def run(args: argparse.Namespace, p: Platform) -> None:
    c = p.container
    platform_uow = SqlTenancyUnitOfWork(c.session_factory, None)

    if args.command == "create-superadmin":
        password = _secret("Password (min 10 chars): ")
        user_id = await p.identity.create_user(
            CreateUserCommand(args.email, args.name, password, SYSTEM, is_super_admin=True)
        )
        print(f"Super-admin created: {user_id}")

    elif args.command == "create-tenant":
        tenant = await CreateTenant(platform_uow, c.clock, c.ids)(
            CreateTenantCommand(
                args.name, args.slug, SYSTEM, timezone=args.timezone, modules=tuple(args.module)
            )
        )
        print(f"Tenant created: {tenant.id} ({tenant.slug})")

    elif args.command == "add-member":
        tenant_id = await _tenant_id(p, args.tenant)
        password = _secret("Initial password (ignored if the user exists): ")
        member = await p.identity.add_member(
            AddMemberCommand(tenant_id, args.email, args.name, Role(args.role), SYSTEM, password)
        )
        print(f"{member.email} is now {member.role} of {args.tenant}")

    elif args.command == "connect-whatsapp":
        tenant_id = await _tenant_id(p, args.tenant)
        number = await ConnectWhatsAppNumber(platform_uow, c.clock, c.ids)(
            ConnectWhatsAppNumberCommand(
                tenant_id, args.phone_number_id, args.display_phone, SYSTEM
            )
        )
        print(f"Connected {number.display_phone} -> {args.tenant}")

    elif args.command == "set-credentials":
        token = _secret("Meta access token: ", confirm=False)
        await SetCredentials(c.credentials)(SetCredentialsCommand(args.phone_number_id, token))
        print("Stored (encrypted).")

    elif args.command == "simulate":
        await _simulate(p, args)

    elif args.command == "seed-demo":
        if not c.settings.is_local:
            sys.exit("seed-demo is for local development only")
        password = _secret("Password for the demo logins (min 10 chars): ")
        print("Creating the demo clinic (takes about 30 s)...")
        print(await seed_demo(c.settings, password, reset=args.reset))

    elif args.command == "tick":
        jobs_uow = SqlJobsUnitOfWork(c.session_factory)
        events = await DispatchOutbox(jobs_uow, c.event_handlers, c.clock)()
        jobs = await RunDueJobs(jobs_uow, c.job_handlers, c.clock)()
        print(f"events: {events}\njobs:   {jobs}")


async def _simulate(p: Platform, args: argparse.Namespace) -> None:
    """Chat with the bot exactly as WhatsApp would, but in the terminal (RecordingGateway)."""
    gateway = p.container.whatsapp_gateway
    if not isinstance(gateway, RecordingGateway):
        sys.exit("simulate needs WHATSAPP_SENDER=recording (it must not message real people)")
    tenant_id = await _tenant_id(p, args.tenant)
    numbers = await ListWhatsAppNumbers(SqlTenancyUnitOfWork(p.container.session_factory, None))(
        tenant_id
    )
    if not numbers:
        sys.exit("Connect a WhatsApp number first (locally any digits work): connect-whatsapp ...")
    phone_number_id = numbers[0].phone_number_id
    scripted: list[str] | None = list(args.text) if args.text else None
    if scripted is None:
        print(
            f"Chatting with {args.tenant} as {args.sender}. Type a message; a number picks a "
            "button; an empty line quits.\n"
        )
    choices: tuple[Choice, ...] = ()
    while True:
        if scripted is not None:
            if not scripted:
                return
            text = scripted.pop(0)
            print(f"you> {text}")
        else:
            text = (await asyncio.to_thread(input, "you> ")).strip()
            if not text:
                return
        kind, choice_id = InboundKind.TEXT, None
        if text.isdigit() and 0 < int(text) <= len(choices):
            picked = choices[int(text) - 1]
            kind, choice_id, text = InboundKind.CHOICE, picked.id, picked.title
        message = InboundMessage(
            phone_number_id=phone_number_id,
            wa_message_id=f"wamid.sim.{uuid4().hex}",
            wa_id=args.sender,
            profile_name=args.name,
            sent_at=datetime.now(UTC),
            kind=kind,
            text=text,
            choice_id=choice_id,
        )
        already = len(gateway.sent)
        await p.conversations.handle_webhook(WebhookBatch(messages=[message], statuses=[]))
        for sent in gateway.sent[already:]:
            print(_render(sent.message))
            choices = _choices(sent.message) or choices


def _choices(message: OutboundMessage) -> tuple[Choice, ...]:
    return message.choices if isinstance(message, Buttons | ListMenu) else ()


def _render(message: OutboundMessage) -> str:
    return "bot> " + message.as_text().replace("\n", "\n     ") + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.bootstrap.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    cmd = sub.add_parser("create-superadmin")
    cmd.add_argument("--email", required=True)
    cmd.add_argument("--name", required=True)

    cmd = sub.add_parser("create-tenant")
    cmd.add_argument("--name", required=True)
    cmd.add_argument("--slug", required=True)
    cmd.add_argument("--timezone", default="Asia/Kolkata")
    cmd.add_argument("--module", action="append", default=[], help="repeatable")

    cmd = sub.add_parser("add-member")
    cmd.add_argument("--tenant", required=True, help="tenant slug")
    cmd.add_argument("--email", required=True)
    cmd.add_argument("--name", required=True)
    cmd.add_argument("--role", required=True, choices=[r.value for r in Role])

    cmd = sub.add_parser("connect-whatsapp")
    cmd.add_argument("--tenant", required=True, help="tenant slug")
    cmd.add_argument("--phone-number-id", required=True)
    cmd.add_argument("--display-phone", required=True)

    cmd = sub.add_parser("set-credentials")
    cmd.add_argument("--phone-number-id", required=True)

    cmd = sub.add_parser("simulate")
    cmd.add_argument("--tenant", required=True, help="tenant slug")
    cmd.add_argument("--from", dest="sender", default="919800000001", help="sender wa_id")
    cmd.add_argument("--name", default="Test Patient", help="WhatsApp profile name")
    cmd.add_argument(
        "--text", action="append", help="scripted message (repeatable); omit for interactive"
    )

    sub.add_parser("tick")
    cmd = sub.add_parser("seed-demo")
    cmd.add_argument("--reset", action="store_true", help="delete the demo clinic first")

    args = parser.parse_args()
    platform = build_platform(get_settings())

    async def _main() -> None:
        try:
            await run(args, platform)
        except DomainError as exc:
            sys.exit(f"Error ({exc.code}): {exc.message}")
        finally:
            await platform.container.engine.dispose()

    asyncio.run(_main())


if __name__ == "__main__":
    main()
