# WhatsApp Business Automation Platform

Multi-tenant platform that automates WhatsApp Business conversations. First module: **appointment scheduling for clinics**.

- **What it does:** [docs/PRD.md](docs/PRD.md)
- **How it is built:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Read §3 (layer rules) and §11 (cookbook) before changing code.
- **Full setup (Meta WhatsApp, QR code demo, payments, Vercel):** [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md)

| Part | Stack | Folder |
|---|---|---|
| API, WhatsApp bot, jobs | Python 3.12, FastAPI, SQLAlchemy 2 (async), PostgreSQL, Alembic | [backend/](backend/) |
| Dashboard | React 19, TypeScript, Vite, TanStack Query, Tailwind | [frontend/](frontend/) |
| Hosting | Vercel (2 projects: `api` = backend/, `web` = frontend/) + Neon/Supabase Postgres | `*/vercel.json` |

## Run it locally

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 24+, and Docker (or any PostgreSQL 17).

```bash
# 1. Database (creates roles app_owner / app_rw / app_purge)
docker compose up -d db

# 2. Backend → http://localhost:8000/docs
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# First run only: create yourself, a clinic, and its first admin (passwords are prompted)
uv run python -m app.bootstrap.cli create-superadmin --email you@example.com --name "You"
uv run python -m app.bootstrap.cli create-tenant --name "Sunrise Clinic" --slug sunrise-clinic --module appointments
uv run python -m app.bootstrap.cli add-member --tenant sunrise-clinic --email admin@example.com --name "Clinic Admin" --role admin
# Optional: a demo clinic full of realistic data (bookings, payments, inbox, privacy requests).
# Logins: admin@sunrise.demo / reception@sunrise.demo / dr.mehta@sunrise.demo (password prompted)
uv run python -m app.bootstrap.cli seed-demo        # add --reset to delete and recreate the demo clinic
# Background jobs: Vercel Cron calls /internal/jobs/tick every minute; locally run it by hand:
uv run python -m app.bootstrap.cli tick

# Chat with the bot in the terminal (no Meta needed; WHATSAPP_SENDER=recording):
uv run python -m app.bootstrap.cli connect-whatsapp --tenant sunrise-clinic --phone-number-id 100000000000001 --display-phone "+91 98765 43210"
uv run python -m app.bootstrap.cli simulate --tenant sunrise-clinic

# 3. Dashboard → http://localhost:5173 (sign in with the admin you just created)
#    API on another port? API_PROXY_TARGET=http://localhost:8010 npm run dev
cd ../frontend
cp .env.example .env.local
npm install
npm run dev
```

## Connecting a real WhatsApp number (Meta Cloud API)

1. In the Meta app: Webhooks → callback URL `https://<api-domain>/webhooks/whatsapp`,
   verify token = `META_VERIFY_TOKEN`; subscribe to the `messages` field.
2. Set `WHATSAPP_SENDER=meta`, `META_APP_SECRET` (App settings → Basic) and `CREDENTIALS_KEY`.
3. `cli connect-whatsapp ...` with the number's **phone number ID**, then
   `cli set-credentials --phone-number-id ...` (the access token is prompted and stored encrypted).

## Checks (the same ones CI runs)

```bash
cd backend  && uv run ruff check . && uv run mypy && uv run lint-imports && uv run pytest
cd frontend && npm run check && npm run build
```

Tests marked `db` need PostgreSQL: set `TEST_DATABASE_URL` (role `app_rw`, e.g. the value of
`DATABASE_URL`) after `alembic upgrade head`; without it they are skipped. Retention tests also use
role `app_purge`: by default the same URL with `app_purge:app_purge`, or set `TEST_DATABASE_PURGE_URL`.

## Reminders and WhatsApp templates

Patients get reminders at the times set in Settings → Booking rules (default 24 h and 2 h before). Each reminder has Confirm, Reschedule and Cancel buttons, plus Pay now when the consultation fee is still due.

WhatsApp only allows **approved templates** more than 24 hours after a patient's last message. For each message listed under Settings → WhatsApp templates:
1. Create a template in WhatsApp Manager with the variables and quick-reply buttons in the order shown.
2. Wait for Meta to approve it.
3. Enter its name.

Until a template is entered, that message is skipped for patients outside the window.

## Live dashboard

The dashboard updates by itself the moment something changes: a new request, a WhatsApp message, a payment or a deletion request. It uses one streaming connection (`/api/live`) per open tab, and polls every 60 s as a backup. No extra service is needed.

## AI understanding (optional)

Patients can type things like "day after tomorrow evening" or "I need to move my visit". The bot's own rules try first. If they fail and AI understanding is on, Claude reads that one message.

**To turn it on:**
1. On the server, set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`.
2. Each clinic ticks the AI understanding box under Settings → Booking rules.

Only the message text is sent, never names or phone numbers. If the AI is unavailable, the bot asks again as usual.

## Payments

Clinics choose any of **WhatsApp Pay**, **Razorpay links** and **Pay at clinic** in Settings → Payments, and set the consultation fee in Settings → Booking rules. When an appointment is confirmed, the patient gets a "Pay now" message (or "payable at the clinic"). Staff can mark payments paid or refunded, or cancel them, on the **Payments** page.

- **Razorpay:** save the key secret and webhook secret (this needs `CREDENTIALS_KEY`), then point a Razorpay webhook at the path shown in settings.
- **WhatsApp Pay:** link the clinic's payment account in WhatsApp Business Manager and enter its configuration name.
- **Record keeping:** payment records are never deleted.

## Data retention

A daily job (20:00 UTC, scheduled by the cron tick) deletes closed cases after 60 days and inactive
open cases after 12 months. Each clinic can change both periods in Settings → Booking rules. A WhatsApp
contact is deleted once it has no patients and has been quiet for 60 days. Patients can type
`DELETE MY DATA`, and staff approve or reject the request on the **Privacy** page. Payment records are
never deleted. Purges use the `app_purge` database role (`DATABASE_PURGE_URL`); in production use
its pooled connection string, like `DATABASE_URL`.

`uv run lint-imports` and `npm run lint` enforce the architecture's layer rules. If they fail, the code
is in the wrong layer; move it rather than silencing the rule.

## Where things go

```
backend/src/app/
  bootstrap/        composition root: settings, container (wiring), installed modules, health
  shared/kernel/    framework-free building blocks (AggregateRoot, DomainEvent, ids, clock, errors)
  shared/…          Unit of Work, DB/RLS session, outbox, error mapping, test fakes
  platform/<x>/     platform core, each with domain/ application/ infrastructure/ presentation/
  modules/<x>/      feature modules (plug-ins); copy modules/_template to start one
frontend/src/
  app/              providers, routes, layout
  shared/           api client (generated types), ui, config
  features/<x>/     api/ → model/ → components/ → pages/, public index.ts
```

After changing backend endpoints, run `npm run gen:api` in `frontend/` and commit `openapi.json` and `schema.d.ts`.
