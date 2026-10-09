# WhatsApp Business Automation Platform

Multi-tenant platform that automates WhatsApp Business conversations. First module: **appointment scheduling for clinics**.

- **What it does:** [docs/PRD.md](docs/PRD.md)
- **How it is built:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Read §3 (layer rules) and §11 (cookbook) before changing code.

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
# Background jobs: Vercel Cron calls /internal/jobs/tick every minute; locally run it by hand:
uv run python -m app.bootstrap.cli tick

# 3. Dashboard → http://localhost:5173 (sign in with the admin you just created)
cd ../frontend
cp .env.example .env.local
npm install
npm run dev
```

## Checks (the same ones CI runs)

```bash
cd backend  && uv run ruff check . && uv run mypy && uv run lint-imports && uv run pytest
cd frontend && npm run check && npm run build
```

Tests marked `db` need PostgreSQL: set `TEST_DATABASE_URL` (role `app_rw`, e.g. the value of
`DATABASE_URL`) after `alembic upgrade head`; without it they are skipped.

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
