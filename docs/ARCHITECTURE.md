# Architecture: WhatsApp Business Automation Platform

| | |
|---|---|
| **Status** | Draft v0.1 |
| **Date** | 2026-10-09 |
| **Implements** | [PRD.md](PRD.md) v0.3 |
| **Audience** | Developers who build and change the code, by hand or with AI help |

> **How to use this document.** Sections 1–4 explain the big picture. Sections 5–9 describe each layer and the platform parts they rely on. Section 10 follows one feature through every layer. Section 11 is a **cookbook**: step-by-step recipes for the changes you will make most often. If you only have five minutes, read §3 (the layer rules) and §11.

---

## 1. Architectural style

| Decision | Choice | Why |
|---|---|---|
| Overall shape | **Modular monolith**: one deployable backend, divided into independent modules | One team, one database and one deploy, which keeps things simple. Module boundaries stay strict, so a module can be split out later if needed. |
| Inside every module | **Layered / hexagonal (ports and adapters)**: `domain` → `application` → `infrastructure` / `presentation` | Business rules have no dependency on FastAPI, SQLAlchemy or WhatsApp, so they are easy to test and to change. |
| Design principles | **SOLID**, enforced by folder structure and by import-linter (§3.4) | Every feature looks the same, so a developer who has changed one feature can change any other. |
| Extensibility | **Registries and plugin contracts** (module definition, router rules, flow steps, job handlers, purgers) | New behaviour is **added**, not edited into existing code (Open/Closed principle, PRD goal G6). |
| Side effects | **Domain events + transactional outbox** | State change and "notify the patient" can never get out of sync. |
| Frontend | **React + TypeScript, feature-sliced** with the same layer idea (api → model → components → pages) | Same mental model on both sides. |

## 2. System context

```
                    ┌──────────────────────────── Vercel (Pro, region bom1) ───────────────────────────┐
 Patient            │                                                                                    │
 (WhatsApp) ◄──► Meta Cloud API ──webhook──► /webhooks/whatsapp ┐                                       │
                    │                                            │   FastAPI app (Python Function)        │
 Razorpay ──webhook─┼──────────────────────► /webhooks/razorpay ─┤   ─ presentation (HTTP, bot flows)    │
                    │                                            │   ─ application (use cases)            │
 Vercel Cron ─every─┼──────────────────────► /internal/jobs/tick ┤   ─ domain (rules)                     │
   minute           │                                            │   ─ infrastructure (DB, adapters)      │
 Vercel Queues ◄────┼──────────── outbox dispatch / consumers ───┘                                        │
                    │                                                     ▲                               │
 Staff/Doctor ──────┼──► React dashboard (static, CDN) ──/api/*──────────┘                               │
 (browser)          └──────────────────────────────────────────────────────┬─────────────────────────────┘
                                                                           │ pooled connection (TLS)
                                                          PostgreSQL (Neon/Supabase, ap-south-1) + RLS
```

## 3. Layer rules (the most important section)

### 3.1 The four layers

| Layer | Contains | May import | Must NOT import |
|---|---|---|---|
| **domain** | Entities, value objects, aggregate methods that enforce the rules, domain services, domain events, domain errors, **repository interfaces** (Protocols) | `shared.kernel`, standard library | FastAPI, Pydantic, SQLAlchemy, httpx, any other module, `application`, `infrastructure`, `presentation` |
| **application** | **Use cases** (one class per command or query), DTOs, **ports** for external services (`MessageSender`, `PaymentGateway`, `Clock`…), the `UnitOfWork` interface | `domain`, `shared` | `infrastructure`, `presentation`, frameworks |
| **infrastructure** | SQLAlchemy tables, repository implementations, mappers, external adapters (Meta, Razorpay, Vercel Queues) | `application`, `domain`, `shared`, frameworks and SDKs | `presentation` |
| **presentation** | FastAPI routers, request/response schemas (Pydantic), WhatsApp **flows and steps**, auth dependencies | `application`, `shared` (and domain **error types** only) | `infrastructure` (it receives use cases already wired) |

```
 presentation ──► application ──► domain ◄── infrastructure
        │                ▲                         │
        └── (wired in) ──┴──── bootstrap ◄─────────┘   (composition root: the only place that knows everything)
```

### 3.2 How SOLID maps to the code

| Principle | How it shows up here | Example |
|---|---|---|
| **S**ingle responsibility | One use case per file. Repositories only save and load. Mappers only convert between objects and rows. A flow step asks exactly **one** question. | `reschedule_appointment.py` contains only `RescheduleAppointment` |
| **O**pen/closed | New behaviour is **registered**, not added by editing a big `if/elif`. Modules, router rules, steps, job handlers, purgers and event handlers all go through registries. | Adding greeting rule R12 = a new `RouterRule` class + one line in the module definition |
| **L**iskov substitution | Every adapter fully honours its port. One **contract-test suite** runs against both the fake and the real implementation. | `FakeAppointmentRepository` and `SqlAppointmentRepository` pass the same tests |
| **I**nterface segregation | Ports are small and named after one capability | `MessageSender`, `TemplateSender` and `MediaUploader` are separate. A use case that only sends text depends only on `MessageSender`. |
| **D**ependency inversion | Use cases depend on `Protocol`s. Concrete classes are chosen **only** in `bootstrap/` | `RescheduleAppointment(uow: UnitOfWork, clock: Clock, …)` |

### 3.3 Rules between modules

- A module may **only** use another module through that module's public `contracts.py` (facades and DTOs) or through **domain events**. Never through its domain, infrastructure or tables.
- Modules never join each other's tables in SQL. If a screen needs data from two modules, the query use case calls both facades.
- `platform/*` modules never import from `modules/*`. Feature modules depend on the platform. The platform never depends on a feature module.

### 3.4 Enforcement

The rules are checked automatically, so they don't depend on people remembering them:

- **Backend:** `import-linter` contracts (layers, independence of modules, platform must not import modules) run in CI and in the pre-commit hook.
- **Frontend:** ESLint `no-restricted-imports` rules in `frontend/eslint.config.js` enforce the same rules for frontend folders (§9).
- **Types:** `mypy --strict` and `tsc --strict`. Any Protocol mismatch fails the build.

---

## 4. Repository layout

```
/
├── backend/
│   ├── pyproject.toml              # uv-managed; ruff, mypy, pytest, import-linter config
│   ├── alembic/                    # migrations (one linear history for the whole monolith)
│   ├── src/app/
│   │   ├── main.py                 # FastAPI app factory → exported `app` (Vercel entrypoint)
│   │   ├── bootstrap/              # COMPOSITION ROOT
│   │   │   ├── settings.py         #   env-based settings (pydantic-settings)
│   │   │   ├── container.py        #   builds adapters + use cases; no business logic
│   │   │   └── modules.py          #   INSTALLED_MODULES = [appointments.module, …]
│   │   ├── shared/
│   │   │   ├── kernel/             # Entity, AggregateRoot, ValueObject, DomainEvent, DomainError,
│   │   │   │                       # TenantId, Ids (UUIDv7), Clock & IdGenerator ports, Result types
│   │   │   ├── application/        # UnitOfWork protocol, EventBus protocol, pagination, auth context
│   │   │   └── infrastructure/     # db engine/session, base SQLAlchemy repo, outbox, RLS session hook
│   │   ├── platform/               # PLATFORM CORE (PRD §6). Each has domain/application/infrastructure/presentation
│   │   │   ├── tenancy/            # tenants, locations, WA numbers, module enablement
│   │   │   ├── identity/           # users, roles, permissions, JWT auth
│   │   │   ├── contacts/           # contacts, consent, opt-out
│   │   │   ├── conversations/      # inbound pipeline, session, router, flow engine (§7)
│   │   │   ├── messaging/          # outbound message model, MessagingGateway, Meta adapter, templates
│   │   │   ├── inbox/              # conversation log, handover
│   │   │   ├── payments/           # PaymentRequest, ledger, PaymentGateway (WhatsApp Pay + Razorpay adapters)
│   │   │   ├── jobs/               # ScheduledJob, JobScheduler, tick runner, handler registry
│   │   │   ├── retention/          # retention orchestrator + Purger protocol, DeletionRecord
│   │   │   └── audit/              # AuditLog
│   │   └── modules/                # FEATURE MODULES (plug-ins)
│   │       └── appointments/
│   │           ├── module.py       # ModuleDefinition: everything this module registers (§8)
│   │           ├── contracts.py    # public facade + DTOs for other modules
│   │           ├── domain/
│   │           │   ├── appointment.py      # Appointment aggregate + state machine
│   │           │   ├── case.py             # Case aggregate
│   │           │   ├── patient.py
│   │           │   ├── doctor.py           # Doctor, WorkingHours, BlockedTime
│   │           │   ├── slot.py             # Slot value object (doctor, start, end)
│   │           │   ├── availability.py     # domain service: free slots
│   │           │   ├── events.py           # AppointmentRequested, Rescheduled, …
│   │           │   ├── errors.py           # SlotUnavailable, InvalidTransition, …
│   │           │   └── repositories.py     # Protocols: AppointmentRepository, …
│   │           ├── application/
│   │           │   ├── commands/           # request_appointment.py, approve_request.py, reschedule_appointment.py …
│   │           │   ├── queries/            # list_appointments.py, get_appointment_detail.py, find_free_slots.py …
│   │           │   ├── event_handlers/     # on_payment_succeeded.py, notify_patient_on_confirmed.py …
│   │           │   ├── jobs/               # send_reminder.py, expire_request.py
│   │           │   └── dto.py
│   │           ├── infrastructure/
│   │           │   ├── tables.py           # SQLAlchemy Table/ORM definitions
│   │           │   ├── mappers.py          # row ⇄ domain
│   │           │   ├── repositories.py     # Sql*Repository implementations
│   │           │   └── purger.py           # CasePurger (retention)
│   │           ├── presentation/
│   │           │   ├── http/               # routers.py, schemas.py
│   │           │   └── whatsapp/
│   │           │       ├── rules.py        # RouterRules R1–R11
│   │           │       ├── flows/          # booking.py, reschedule.py, cancel.py, delete_my_data.py
│   │           │       ├── steps/          # ask_doctor.py, ask_date.py, ask_slot.py, confirm.py …
│   │           │       └── locales/en.yaml # every bot sentence (PRD OQ-7)
│   │           └── tests/                  # unit/, integration/, flows/  (mirror of the layers)
│   └── tests/                      # cross-module + architecture tests, fixtures, fakes
├── frontend/
│   ├── package.json  vite.config.ts  tsconfig.json
│   └── src/  (see §9)
├── docs/  PRD.md  ARCHITECTURE.md  adr/
├── docker-compose.yml              # local Postgres (+ optional Docker image of the API)
├── backend/vercel.json, frontend/vercel.json   # one per Vercel project (crons, rewrites)
└── .github/workflows/ci.yml
```

Every module, platform or feature, has the **same four folders**. Once you have found your way around one module, you can find your way around all of them.

---

## 5. Domain layer

### 5.1 Building blocks (`shared/kernel`)

```python
# shared/kernel/entity.py
@dataclass(eq=False)
class AggregateRoot:
    id: UUID
    tenant_id: TenantId
    version: int = 0                       # optimistic locking
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    def record(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events, self._events = self._events, []
        return events
```

- **Entities and aggregates** are plain `@dataclass`es. The state they hold must always be valid. They only change through methods that are named after business actions (`approve`, `reschedule`), never through setters.
- **Value objects** are `@dataclass(frozen=True)`, for example `Slot`, `PhoneNumber` (normalises to E.164), `Money` and `Reference`.
- **Domain errors** subclass `DomainError(code: str)`. The presentation layer turns the code into an HTTP status or a bot message (§6.4).
- The domain never reads the clock or generates IDs itself. Both come in as arguments, so tests are deterministic.

### 5.2 The Appointment aggregate (status lifecycle from PRD §7.6)

```python
# modules/appointments/domain/appointment.py
ACTIVE = {Status.REQUESTED, Status.CONFIRMED, Status.RESCHEDULED}

_ALLOWED: dict[Status, set[Status]] = {
    Status.REQUESTED:   {Status.CONFIRMED, Status.DECLINED, Status.EXPIRED, Status.CANCELLED},
    Status.CONFIRMED:   {Status.RESCHEDULED, Status.CANCELLED, Status.COMPLETED, Status.NO_SHOW},
    Status.RESCHEDULED: {Status.RESCHEDULED, Status.CANCELLED, Status.COMPLETED, Status.NO_SHOW},
}

@dataclass(eq=False)
class Appointment(AggregateRoot):
    reference: Reference
    case_id: UUID
    patient_id: UUID
    slot: Slot
    original_slot: Slot
    status: Status
    reason: str | None

    def reschedule(self, new_slot: Slot, actor: Actor, at: datetime) -> None:
        self._transition(Status.RESCHEDULED)
        if new_slot == self.slot:
            raise SameSlot()
        old, self.slot = self.slot, new_slot
        self.record(AppointmentRescheduled(self.id, old=old, new=new_slot, actor=actor, at=at))

    def _transition(self, to: Status) -> None:
        if to not in _ALLOWED.get(self.status, set()):
            raise InvalidTransition(self.status, to)
        self.status = to
```

Domain events are **also the appointment history** (PRD §7.8). The repository saves every event that was pulled to `appointment_events`, so state and history are always written in the same transaction (DR-4).

### 5.3 Repository ports

```python
# modules/appointments/domain/repositories.py
class AppointmentRepository(Protocol):
    async def get(self, id: UUID) -> Appointment: ...                       # raises AppointmentNotFound
    async def get_for_update(self, id: UUID) -> Appointment: ...            # row lock
    async def list_active_for_patient(self, patient_id: UUID) -> list[Appointment]: ...
    async def add(self, appointment: Appointment) -> None: ...
    async def save(self, appointment: Appointment) -> None: ...             # checks version
```

Tenant filtering is **not** a parameter. The Unit of Work is already scoped to one tenant (§8.2), so a repository cannot accidentally query across tenants.

---

## 6. Application layer

### 6.1 Use case pattern (every command looks like this)

```python
# modules/appointments/application/commands/reschedule_appointment.py
@dataclass(frozen=True)
class RescheduleAppointmentCommand:
    appointment_id: UUID
    new_start: datetime
    actor: Actor                      # contact / staff:<id> / system
    channel: Channel                  # whatsapp / dashboard / scheduler

class RescheduleAppointment:
    def __init__(self, uow: AppointmentsUnitOfWork, clock: Clock, policy: ReschedulePolicy) -> None:
        self._uow, self._clock, self._policy = uow, clock, policy

    async def __call__(self, cmd: RescheduleAppointmentCommand) -> AppointmentDTO:
        async with self._uow as uow:
            appt = await uow.appointments.get_for_update(cmd.appointment_id)
            doctor = await uow.doctors.get(appt.slot.doctor_id)
            new_slot = doctor.slot_starting_at(cmd.new_start)          # validates working hours
            self._policy.ensure_can_change(appt, now=self._clock.now())  # cut-off (AP-4.8)
            await uow.reservations.move(appt.id, new_slot)             # DB exclusion constraint guards (AP-2.6)
            appt.reschedule(new_slot, cmd.actor, self._clock.now())
            await uow.appointments.save(appt)
            await uow.commit()                                         # state + events + outbox, one txn
        return AppointmentDTO.from_domain(appt)
```

Conventions:

- **One class, one `__call__`.** Its inputs are a frozen `…Command` or `…Query` dataclass. It returns a DTO, never a domain object.
- Use cases **orchestrate**. The business rules themselves live in the domain (aggregate methods, policies and domain services).
- **Queries** may skip the domain and read with optimised SQL through a `…ReadModel` port. Commands always go through aggregates.
- The **bot and the dashboard call the same use case**. Only the `actor` and `channel` values differ (PRD §5, "System (bot)").

### 6.2 Unit of Work

```python
class AppointmentsUnitOfWork(UnitOfWork, Protocol):
    appointments: AppointmentRepository
    cases: CaseRepository
    patients: PatientRepository
    doctors: DoctorRepository
    reservations: SlotReservationRepository
```

When `commit()` runs:

1. Each changed aggregate's `pull_events()` is collected.
2. The events are saved to the module's history table (when one exists) **and** to `outbox`.
3. The database transaction is committed.
4. After the commit, the outbox dispatcher is told there is work (§8.4).

### 6.3 Ports owned by the application layer

| Port | Purpose | Implementations |
|---|---|---|
| `Clock` | Current time | `SystemClock`, `FrozenClock` (tests) |
| `IdGenerator` | UUIDv7 and short references | `Uuid7Generator`, `SequentialIds` (tests) |
| `MessageSender` / `TemplateSender` | Send WhatsApp messages | `MetaCloudSender`, `RecordingSender` (tests) |
| `PaymentGateway` | Create a payment request, verify and parse its webhook, refund | `WhatsAppPayGateway`, `RazorpayLinkGateway`, `AtClinicGateway`, `FakePaymentGateway` (tests) |
| `JobScheduler` | Schedule or cancel a future job | `PostgresJobScheduler` |
| `TaskQueue` | Async work | `VercelQueue`, `InlineQueue` (local and tests) |
| `RealtimePublisher` | Push updates to the dashboard | `NoopPublisher` (v1, polling), `AblyPublisher` (later) |
| `DateTimeParser` | Turn "sat 5pm" into a datetime | `RuleBasedParser` (v1), `LlmParser` (Phase 2) |
| `AuditLogger` | Record access to personal data | `SqlAuditLogger` |

### 6.4 Errors

There is one mapping table for each output channel:

```python
# presentation/http/errors.py                     # presentation/whatsapp/errors.py
HTTP_STATUS = {                                   BOT_MESSAGE = {
  "appointment.not_found": 404,                     "appointment.slot_unavailable": "errors.slot_taken",
  "appointment.slot_unavailable": 409,              "appointment.cutoff_passed":    "errors.too_late",
  "appointment.invalid_transition": 409,            …
  "concurrency.conflict": 409, …                  }
}
```

---

## 7. Conversation engine (platform/conversations)

### 7.0 Where the pieces live (as built)

- **Plug-in API** (`app/shared/application/conversation.py`): `Step`, `BaseStep`, `Flow`, `RouterRule`, `FlowContext`, `InboundReply`, results `Next / Retry / Finish / StartFlow`. Modules write flows against this only.
- **Message types** (`app/shared/kernel/messages.py`): `Text`, `Buttons`, `ListMenu`, `Template`, `menu()`. **Sending** from any module: the `Messenger` port (`services.messenger`), which enforces the 24-hour window, logs the message and retries transient failures (`messaging.retry_send` job).
- **Engine** (`app/platform/conversations`): pipeline, router, flow registry, sessions, global commands (STOP / START / MENU / AGENT), `AskConsent` step (via `conversations.contracts.consent_step`).
- **A module's flow** = steps in `presentation/whatsapp/steps.py`, rules in `presentation/whatsapp/rules.py`, the `Flow(...)` assembled in the module's `wiring.py` (it combines presentation + infrastructure, so it is composition), texts in `locales/en.toml`.
- **Contracts vs integration:** a module's `contracts.py` exports only framework-free types (safe for other modules' application layers); wiring-level helpers go in `integration.py` (e.g. `messaging.integration`). import-linter enforces this.
- **Safety net:** the webhook stores each message first (unique `wa_message_id`), schedules `conversations.process_inbound` for +2 min, processes, then cancels the job. A crash mid-processing is retried by the job; a Meta re-delivery is recognised as a duplicate.

### 7.1 Inbound pipeline: a chain of responsibility (PRD PL-3.2)

```
Webhook ─► VerifySignature ─► Dedupe(wa_message_id) ─► ResolveTenant(phone_number_id)
        ─► ResolveContact ─► LockSession(contact) ─► HandoverGate ─► GlobalCommands
        ─► ContinueActiveFlow ─► Router(rules by priority) ─► Flow.start
```

- Each stage is a class with `async handle(ctx, next)`. Stages are listed once in `conversations/pipeline.py`. Adding a stage (for example spam filtering) means inserting one class.
- `LockSession` runs `SELECT … FOR UPDATE` on the contact's session. If a contact sends two quick messages, they are processed one at a time.
- The webhook **saves the inbound message first** (`status=received`), processes it inline within a time budget, and then returns 200. If processing fails, the cron tick tries again (`received` → `processed`), so no message is lost.

### 7.2 Router rules (PRD §7.1, R1–R11)

```python
class RouterRule(Protocol):
    priority: int                                    # lower = checked first
    async def matches(self, ctx: ConversationContext) -> bool: ...
    async def start(self, ctx: ConversationContext) -> FlowStart: ...
```

The appointments module registers `HandoverActiveRule` (R8), `OptedOutRule` (R9), `InterruptedFlowRule` (R7), `MultiPatientRule` (R4), `PendingRequestRule` (R5), `PaymentDueRule` (R6), `WithinCutoffRule` (R10), `ActiveAppointmentRule` (R2), `ReturningPatientRule` (R3) and `NewContactRule` (R1, the fallback). The router contains no `if contact is new …` logic. It simply runs the first rule that matches.

### 7.3 Flows and steps

```python
class Step(Protocol):
    key: str
    async def prompt(self, ctx: FlowContext) -> OutboundMessage: ...
    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult: ...
    # StepResult = Next(step_key) | Stay(error_key) | Done(outcome) | Skip   ← Skip when data already known (DR-5)

booking_flow = Flow(
    key="appointments.booking",
    steps=[AskConsent(), ChoosePatient(), AskName(), AskLocation(), AskDoctor(),
           AskDate(), AskSlot(), AskReason(), AskCustomFields(), ConfirmBooking()],
)
```

- Each step **skips itself** when the data is already known. For example, `AskName` returns `Skip` when the patient's name is stored. This is how "never ask again" (G2) is built.
- Steps call **use cases** (for example `FindFreeSlots` or `RequestAppointment`). They never call repositories.
- `OutboundMessage` doesn't depend on any channel: `Text`, `Buttons`, `List` or `Template`. The Meta adapter turns it into WhatsApp JSON. If buttons aren't possible, it falls back to a numbered text menu (PL-3.4).
- All text comes from `locales/<lang>.yaml` keys. Code never contains sentences shown to patients.
- The session stores `{flow_key, step_key, data, attempts, expires_at}`. After 3 failed attempts at the same step, the conversation is handed over to staff (PL-5.3).

---

## 8. Platform services

### 8.1 Module plugin contract (PRD G6)

```python
# modules/appointments/module.py
module = ModuleDefinition(
    key="appointments",
    http_routers=[appointments_router, requests_router, settings_router],
    router_rules=[NewContactRule(), ReturningPatientRule(), ActiveAppointmentRule(), …],
    flows=[booking_flow, reschedule_flow, cancel_flow, delete_my_data_flow],
    menu_items=[…],
    job_handlers={"appointments.send_reminder": SendReminder, "appointments.expire_request": ExpireRequest},
    event_handlers={PaymentSucceeded: [MarkAppointmentPaid], AppointmentConfirmed: [NotifyPatient, ScheduleReminders]},
    purgers=[CasePurger],
    settings_schema=AppointmentSettings,       # per-tenant module settings (Pydantic)
)
```

`bootstrap/modules.py` lists the installed modules. When the app starts, the container goes through each module and registers its routers, rules, flows, handlers and purgers. **The platform core never imports a module by name.**

### 8.2 Tenancy and row-level security

- Every tenant-owned table has `tenant_id uuid not null` and an RLS policy `USING (tenant_id = current_setting('app.tenant_id')::uuid)`, with `FORCE ROW LEVEL SECURITY` turned on.
- When the UoW opens a transaction it runs `SET LOCAL app.tenant_id = …`. `SET LOCAL` only lasts for one transaction, so it is **safe with transaction-mode connection pooling**.
- The tenant comes from the JWT on dashboard requests, from `phone_number_id` on webhooks, and from the job row for jobs.
- The app connects as the DB role `app_rw`, which is not the table owner, so RLS applies. Migrations run as `app_owner`. The retention purge runs as `app_purge`, the only role allowed to DELETE history and event tables (PRD §11). Platform super-admin endpoints use a separate code path that sets no tenant and is audited.

### 8.3 Preventing double-booking

There is a single `slot_reservations` table (`appointment_id`, `doctor_id`, `start_at`, `end_at`, `kind` = appointment | reschedule, `active`). Every booking, reschedule and reschedule hold goes through `SlotReservations.reserve()`, which:

1. takes a transaction-scoped advisory lock for that doctor (`pg_advisory_xact_lock(hashtextextended('doctor:<id>', 0))`), so concurrent bookings for the same doctor run one after the other, and
2. refuses the slot if another appointment's active reservation overlaps it (`SlotUnavailable` → the bot offers other times; the API returns 409).

An appointment never conflicts with its own reservations, so moving it by 15 minutes works. Cancel, decline, expiry and attendance release reservations; approving a reschedule promotes the hold. This needs no PostgreSQL extension, so it runs the same on Neon/Supabase, in CI and on a local embedded PostgreSQL. It is proven by `test_two_simultaneous_bookings_for_one_slot_only_one_wins` (PRD AC-8). (The original plan was a `btree_gist` exclusion constraint; see ADR-005.)

Every Unit of Work also runs `set_config('TimeZone', 'UTC', true)`, so timestamps always come back in UTC whatever the server's default timezone is.

Conflicting edits to the same appointment are caught by **optimistic locking** (a `version` column). The losing request gets `ConcurrencyConflict` (409) and is asked to retry.

### 8.4 Events, outbox and async work

```
use case ─► aggregate.record(event) ─► UoW.commit: [state + history + outbox] in ONE txn
                                              │
               after commit ─► OutboxDispatcher ─► in-process handlers (fast, e.g. RealtimePublisher)
                                              └─► TaskQueue (Vercel Queues) ─► consumer ─► handler (send WhatsApp messages, payment requests)
         cron tick (every minute) ─► re-dispatch outbox rows still undelivered after 1 min
```

- Until the queue kick is added with messaging (step 3), the outbox is drained by the cron tick, so handlers run within about a minute of the commit.
- Every handler is **idempotent**, keyed on `event_id`. The outbox guarantees each event is delivered *at least once*; idempotent handlers make processing it twice harmless.
- Use cases never call `MessageSender` directly to send notifications. They record an event, and a handler sends the message. This keeps use cases small and makes notifications reliable.

### 8.5 Scheduled jobs (reminders, expiries, retention)

- `JobScheduler.schedule(type, run_at, payload, idempotency_key)` inserts into `scheduled_jobs`. `cancel(idempotency_key)` cancels the job, for example when an appointment is rescheduled and its reminders need to move.
- **Vercel Cron** → `GET /internal/jobs/tick` (requires `CRON_SECRET`) every minute. Each tick claims due rows with `FOR UPDATE SKIP LOCKED LIMIT n`, runs the handlers from the registry, marks them done, and retries failures with back-off. Each tick stops after roughly 50 s so it finishes inside the function's time limit.
- The daily retention job also runs through the tick (`platform.retention.run` with a daily `run_at`).

### 8.6 Payments (three methods, one interface)

```python
class PaymentGateway(Protocol):
    key: str                                                         # "whatsapp_pay" | "razorpay_link" | "at_clinic"
    async def create(self, req: PaymentRequest, contact: Contact) -> GatewayResult: ...   # sends/returns what the patient taps
    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> PaymentStatusUpdate | None: ...  # verifies signature
    async def refund(self, req: PaymentRequest) -> None: ...         # WhatsApp Pay raises RefundNotSupported → staff use Mark as refunded
```

| Option | `create` | Status arrives on | Refund |
|---|---|---|---|
| **A: WhatsApp Payments** (`WhatsAppPayGateway`) | Sends a WhatsApp **order details** ("Review and pay") message using the tenant's payment configuration from WhatsApp Business Manager (for example Razorpay linked there) | `/webhooks/whatsapp` (the inbound pipeline passes payment statuses to payments) | Outside the system, then **Mark as refunded** |
| **B: Razorpay link** (`RazorpayLinkGateway`) | Creates a Razorpay payment link with the tenant's keys, then the bot sends it with a **Pay now** button | `/webhooks/razorpay` | From the dashboard through the Razorpay API |
| **C: Pay at clinic** (`AtClinicGateway`) | Sends nothing. The request stays `PENDING` and shows "due at clinic" | Staff **Mark as paid** (cash or UPI at the counter) | **Mark as refunded** |

- The tenant turns on any combination of the three methods. If more than one is on, the bot step `ChoosePaymentMethod` asks the patient (it **skips** itself when only one is on). `container.py` builds a `PaymentGatewayRegistry` keyed by `key`, and the use case gets the chosen gateway from it. **No use case knows which method is in use.**
- `platform/payments` owns `PaymentRequest(subject_type, subject_id, amount, status, gateway, gateway_ref)` and the **ledger** (PRD RT-7). It knows nothing about appointments. The appointments module talks to it through the payments facade and hears back through the `PaymentSucceeded`, `PaymentFailed` and `PaymentRefunded` events.
- Status changes come **only** from a verified, deduplicated webhook (unique `provider_event_id`) or from staff actions with the `payment.mark` permission (**Mark as paid / Mark as refunded**). Every change is audited (PL-6.4).

### 8.7 Retention and deletion (PRD §7.10)

```python
class Purger(Protocol):
    async def due(self, now: datetime, settings: RetentionSettings) -> list[PurgeTarget]: ...
    async def purge(self, target: PurgeTarget) -> PurgeCounts: ...    # runs as app_purge role
```

`RetentionOrchestrator` runs every registered purger, skips anything blocked by RT-6 (an active appointment, a pending payment or a legal hold), and writes one `DeletionRecord` for each target. When a case is purged, the payments module **detaches** its ledger entries first (`subject_id → NULL`, health fields removed), so payment records survive (RT-7). A "delete my data" request (AP-10.8–13) calls the same purgers straight away.

### 8.8 Auth and permissions

- Passwords are hashed with Argon2. Access tokens are JWTs that last 15 minutes. Refresh tokens last 14 days, are rotated on each use, are stored only as a hash, and are sent in an `httpOnly` cookie.
- Permissions are strings (`appointment.approve`, `inbox.reply`, `settings.manage`, `patient.read`). Each role is a set of permissions stored per tenant.
- Each route declares the permission it needs: `Depends(require("appointment.approve"))`. Use cases receive an `AuthContext` when they need to filter results by user (for example, doctors see only their own appointments).
- Use cases that return or change personal data call the `AuditLogger` port explicitly (`await audit.record(AuditRecord(...))`), which writes to `audit_log` in its own short transaction (PL-8.3). Explicit calls are easier to follow than a decorator.
- Platform-level records (users, tenants, scheduled jobs) extend `AggregateRoot`; everything owned by one tenant extends `TenantAggregateRoot`. Platform tables have no RLS and are only touched by their own module.
- `identity` and `jobs` need more than `PlatformServices` (password hasher, token issuer, handler registries, cron secret), so `app/main.py` wires their routers explicitly; every other module plugs in through `ModuleDefinition.build_routers`.

---

## 9. Frontend architecture (React + TypeScript)

### 9.1 Stack

| Concern | Choice |
|---|---|
| Build | Vite, TypeScript 5.9 `strict` (5.x until openapi-typescript and typescript-eslint support TS 6+) |
| Routing | React Router |
| Server state | **TanStack Query** (caching, retries, polling for "live" lists) |
| API types | **Generated from FastAPI's OpenAPI schema** (`openapi-typescript` + `openapi-fetch`), so backend and frontend types cannot drift apart |
| Forms and validation | react-hook-form + zod |
| UI | Tailwind CSS + shadcn/ui components (copied into `shared/ui`, editable) |
| Tests | Vitest + Testing Library; Playwright for the main end-to-end journeys |
| Boundaries | ESLint `no-restricted-imports` per layer folder (`eslint.config.js`) |

### 9.2 Layout (feature-sliced, mirrors the backend modules)

```
frontend/src/
├── app/                   # providers (QueryClient, Auth, Router), route table, layout shell
├── shared/
│   ├── api/               # generated schema.d.ts + typed client + auth/refresh interceptor
│   ├── ui/                # buttons, tables, dialogs (no business knowledge)
│   ├── lib/               # dates (tenant timezone), formatting, permission helpers
│   └── config/
├── features/
│   ├── auth/
│   ├── requests/          # approval queue (AP-3)
│   ├── appointments/      # list, calendar, detail + timeline (AP-7)
│   ├── inbox/             # conversations, handover (PL-5)
│   ├── cases/             # cases, retention dates, deletion requests (§7.10)
│   └── settings/          # doctors, hours, booking fields, policies, templates
│       └── <each feature>/
│           ├── api/       # useXxxQuery / useXxxMutation hooks (the ONLY place calling the client)
│           ├── model/     # types, mappers, pure helpers (e.g. statusLabel, canReschedule)
│           ├── components/# presentational components; receive data via props
│           ├── pages/     # route-level components; compose hooks + components
│           └── index.ts   # public surface of the feature
└── main.tsx
```

Rules, in the same spirit as the backend:

- `pages` → `components`, `api` and `model`. `components` → `model` and `shared/ui`. `api` → `shared/api`.
- A feature imports another feature **only through its `index.ts`**. `shared` never imports from `features`.
- Components never call `fetch` directly. **All server calls go through `api/` hooks.**
- Permissions shown in the UI (`can("appointment.approve")`) only hide buttons. The real check is always made on the backend.
- "Live" lists (requests queue, inbox) refetch every 10 s and whenever the window regains focus (ADR-007). When a `RealtimePublisher` adapter is added later, it will invalidate the same query keys, so the components don't change.

---

## 10. Worked example: "Reschedule APT-7K3Q from Fri 15:00 to Sat 17:00"

This shows which file does what, in order. Use it as a pattern when building any new feature.

| # | Layer | File | Responsibility |
|---|---|---|---|
| 1 | presentation / whatsapp | `appointments/presentation/whatsapp/rules.py` → `ActiveAppointmentRule` | Patient says "Hi", has an active appointment → show the menu (R2) |
| 2 | presentation / whatsapp | `flows/reschedule.py`: `PickAppointment` → `AskNewDate` → `AskNewSlot` → `ConfirmReschedule` | Ask only what changes (AP-4.2). `PickAppointment` **skips** itself when there is exactly one appointment and asks "which one?" when there are several (AP-4.1). |
| 3 | application / query | `queries/find_free_slots.py` | Lists Saturday's free slots for that doctor |
| 4 | application / command | `commands/request_reschedule.py` (approval on) **or** `commands/reschedule_appointment.py` (approval off) | Puts a hold on the new slot, or moves the appointment straight away |
| 5 | domain | `appointment.py` → `request_reschedule()` / `reschedule()` | Checks the status change is allowed and records `RescheduleRequested` / `AppointmentRescheduled` |
| 6 | infrastructure | `repositories.py` → `SqlAppointmentRepository.save`, `SqlSlotReservationRepository.move` | Version check, exclusion constraint, writes events to `appointment_events` and `outbox` |
| 7 | presentation / http | `http/routers.py` → `POST /requests/{id}/approve` | Staff approve from the dashboard → `ApproveRequest` use case → `appointment.reschedule()` |
| 8 | application / event handler | `event_handlers/notify_patient_on_rescheduled.py`, `reschedule_reminders.py` | Sends the "Done ✅" template and moves the reminder jobs |
| 9 | frontend | `features/requests/api/useApproveRequest.ts` → `components/RequestCard.tsx` → `pages/RequestsPage.tsx` | Approve button, optimistic update, refreshes the appointment detail |
| 10 | frontend | `features/appointments/components/Timeline.tsx` | Shows `RESCHEDULE_REQUESTED` → `RESCHEDULED` (Fri 15:00 → Sat 17:00), who did it, and when |
| 11 | tests | `tests/unit/test_appointment.py`, `tests/flows/test_reschedule_flow.py`, `tests/integration/test_reservations.py` | Domain rules, the whole conversation using fakes, and the double-booking constraint against real Postgres |

---

## 11. Cookbook: common changes, step by step

### 11.1 Add a field to an appointment (e.g. `visit_type`)
1. `domain/appointment.py`: add the attribute, and validate it in the factory or method that sets it.
2. `infrastructure/tables.py` + `mappers.py`: add the column and map it both ways.
3. `alembic revision --autogenerate -m "appointment visit_type"`, then review the migration file.
4. `application/dto.py`: add the field to `AppointmentDTO`.
5. `presentation/http/schemas.py`: add it to the response schema → run `npm run gen:api` in `frontend/`.
6. Frontend: show it in `features/appointments/components/…`.
7. Tests: a domain unit test, and a repository round-trip test.

### 11.2 Add a new use case (e.g. "Mark attendance confirmed")
1. Domain: add an aggregate method `confirm_attendance(actor, at)` and an event `AttendanceConfirmed`.
2. Application: create `commands/confirm_attendance.py` with a `Command` dataclass and a use case class (copy the pattern from §6.1).
3. Bootstrap: wire it up in `container.py`.
4. Presentation: add an HTTP route and/or a bot step that calls it.
5. Tests: a unit test using the fake UoW.

### 11.3 Add a step to a WhatsApp flow (e.g. ask "first visit?")
1. Create the step class in `presentation/whatsapp/steps.py` (subclass `BaseStep`): `prompt` says the question, `handle` returns `Next()` / `Retry("key")` / `Finish()`, `should_skip` returns True if the answer is already known.
2. Add the text keys to `locales/en.toml`.
3. Insert the step in the right place in the `Flow(...)` in the module's `wiring.py`.
4. Add a flow test with `ConversationHarness` (`await chat.send("hi")`, `await chat.tap(1)`): see `modules/_template/tests/test_whatsapp.py`.

### 11.4 Add a greeting/router rule (e.g. R12 "birthday greeting")
Create a class implementing `RouterRule` with the right `priority`, and add it to `module.py → router_rules`. The router and other rules stay as they are.

### 11.5 Swap or add an external provider (e.g. Gupshup instead of Meta)
Implement `MessageSender`/`TemplateSender` in `platform/messaging/infrastructure/gupshup.py`, run the messaging contract tests against it, and choose it in `container.py` based on a setting. No use case changes.

### 11.6 Add a scheduled job
Write a handler class `async __call__(payload)`, register it in `module.py → job_handlers`, and call `JobScheduler.schedule(...)` from an event handler. Make it idempotent.

### 11.7 Add a new module (e.g. `feedback_surveys`)
1. Copy the `modules/_template/` skeleton (the four layers, `module.py` and `contracts.py`).
2. Build its domain, use cases, rules, flows and routers.
3. Add it to `bootstrap/modules.py` and add a migration.
4. Add an import-linter independence contract for it.
5. Frontend: create `features/feedback/` and add a route in `app/`.

### 11.8 Add a dashboard page
Create `features/<x>/api/` (hooks) → `model/` → `components/` → `pages/`, register the route in `app/routes.tsx`, and protect it with `<RequirePermission perm="…">`.

---

## 12. Testing strategy

| Level | Scope | Tools | Speed |
|---|---|---|---|
| Domain unit | Aggregates, value objects, policies, availability | pytest (no I/O) | ms |
| Use case | Commands and queries with **fake** UoW, clock and senders | pytest + `tests/fakes/` | ms |
| Flow | Whole WhatsApp conversations (R1–R11 and edge cases) through the real pipeline, with a `RecordingSender` | pytest | ms |
| Repository / integration | SQL, RLS isolation, exclusion constraint, outbox, purge roles | pytest + **testcontainers Postgres** | s |
| Contract | The same suite run against fake and real adapters (Liskov) | pytest, parametrised | s |
| API | Routers, auth, permission checks, error mapping | httpx `AsyncClient` | s |
| Architecture | Layer and module rules | import-linter, ESLint `no-restricted-imports` | s |
| Frontend | Components and hooks (Vitest + MSW); main journeys (Playwright) | — | s–min |

Every PRD acceptance criterion (§15) has at least one automated test, named after the criterion (`test_ac06_reschedule_keeps_id_and_frees_old_slot`).

---

## 13. Hosting and operations (Vercel)

| Item | Setup |
|---|---|
| Projects | Two Vercel projects from this monorepo: **web** (root `frontend/`) and **api** (root `backend/`). `web` rewrites `/api/*` → `api` so the browser sees one origin (cookies just work). |
| Region | `bom1` for functions. The database is in `ap-south-1`. |
| Database | Neon or Supabase Postgres through the Vercel Marketplace. The **pooled** URL is used at runtime, and the direct URL for migrations. SQLAlchemy async uses **psycopg 3** with `NullPool` and `prepare_threshold=None`, because the external pooler does the pooling. |
| Migrations | Run in CI with `alembic upgrade head` (direct URL, as `app_owner`) **before** the deploy is promoted. |
| Cron | `backend/vercel.json` → `{"path": "/internal/jobs/tick", "schedule": "* * * * *"}` (Pro plan; added with the jobs module in build step 2) |
| Queues | Vercel Queues topics: `outbox`, `outbound-messages` |
| Secrets | Vercel environment variables: `DATABASE_URL`, `DATABASE_DIRECT_URL`, `DATABASE_PURGE_URL`, `JWT_SECRET`, `CRON_SECRET`, `META_APP_SECRET`, per-tenant tokens (stored **encrypted** in the database, with the key in an environment variable) |
| Local development | `docker compose up db` → `uv run fastapi dev` + `npm run dev`. `InlineQueue` replaces Vercel Queues, and `POST /internal/jobs/tick` is triggered by hand or by a small loop. A tunnel (ngrok / cloudflared) is used for Meta webhooks. |
| Portability | `backend/Dockerfile` builds the same app, so it can run on Render, Railway or AWS. Only `container.py` adapter choices change. |
| Observability | `structlog` JSON logs with `tenant_id`, `correlation_id` and `wa_message_id`, and **no personal data**. Errors go to Sentry. Vercel logs and metrics are also available. |
| CI (GitHub Actions) | ruff → mypy → import-linter → pytest (with Postgres service) → frontend lint, typecheck and test → OpenAPI drift check → migrate → deploy |

---

## 14. Architecture decision records

Short ADRs live in `docs/adr/NNN-title.md`. These are the first ones:

| ADR | Decision |
|---|---|
| 001 | Modular monolith with hexagonal layers per module; enforced by import-linter |
| 002 | Manual composition root (`bootstrap/container.py`) instead of a DI framework, because it is explicit and easy to follow and change by hand |
| 003 | Domain events double as appointment history; transactional outbox for side effects |
| 004 | Postgres RLS with `SET LOCAL app.tenant_id` per transaction for tenant isolation |
| 005 | `slot_reservations` + per-doctor advisory lock and overlap check for double-booking protection (no `btree_gist` extension needed) |
| 006 | Jobs table + per-minute Vercel Cron tick instead of a resident worker (fits serverless; portable) |
| 007 | v1 dashboard "real time" = 10 s polling + focus refetch through TanStack Query; push adapter (Ably/Pusher) behind `RealtimePublisher` later |
| 008 | Psycopg 3 + `NullPool` behind an external transaction pooler |
| 009 | OpenAPI-generated TypeScript client as the single source of API types |
| 010 | Bot sentences only in locale files; steps reference keys |
| 011 | UUIDv7 primary keys; human references `APT-XXXX` (Crockford base32, unique per tenant) |

## 15. Build order (maps to PRD §14)

1. ✅ **Skeleton** (done 2026-10-10): repo layout, tooling (uv, ruff, mypy, import-linter, Vite, ESLint), CI, `shared/kernel`, the DB session with RLS, the Alembic baseline, and the `_template` module.
2. ✅ **Platform foundations** (done 2026-10-10): tenancy, identity and auth, contacts, audit, outbox and dispatcher, jobs and tick, dashboard sign-in.
3. ✅ **Messaging + conversations** (done 2026-10-10): Meta webhook and sender, message log, encrypted credentials, inbound pipeline with safety-net job, flow engine, router, global commands, TOML locales, `ConversationHarness` for flow tests, `cli simulate`.
4. ✅ **Appointments domain + use cases** (done 2026-10-10): doctors and availability, reservations, booking and the approval queue, reschedule and cancel, cases, history, dashboard API, request expiry.
5. **Bot rules and flows:** R1–R11, plus flow tests for every PRD acceptance criterion.
6. **Dashboard:** auth, requests queue, appointments list, detail and timeline, settings, inbox and handover.
7. **Retention and deletion:** purgers, the daily job, the `DELETE MY DATA` flow, and the cases UI.
8. **Phase 2:** payments (WhatsApp Payments, Razorpay links, Pay at clinic, Mark as paid/refunded), reminder templates with buttons, `LlmParser`, push real-time updates.
