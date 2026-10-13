# Complete Setup Guide: from zero to a live WhatsApp QR demo

This guide covers every account, key, setting and command you need to run the clinic appointment
bot on a real WhatsApp number. At the end, a patient scans a QR code, WhatsApp opens with "Hi"
already typed, and the bot books an appointment that shows up live in the dashboard.

There are two ways to run it:

| | **Path A: laptop + tunnel** (best for a demo) | **Path B: Vercel production** |
|---|---|---|
| Where it runs | Your Mac, with ngrok/cloudflared giving Meta a public URL | Vercel (API + dashboard) + Neon/Supabase Postgres |
| Cost | Free | Free (Vercel Hobby + Supabase free + cron-job.org) |
| Time | About 1–2 hours, most of it Meta setup | Path A plus about 1 hour |
| Sections | 1 → 9, then 11 | 1, 3, 5–8, then 10 |

Do Path A first. Once the demo works there, moving to Vercel only changes the URLs and env vars.

---

## 1. Accounts and tools checklist

| Need | Why | Where |
|---|---|---|
| **uv**, **Node 24+**, **Docker Desktop** | Backend, dashboard, local Postgres | `brew install uv node` and docker.com |
| **Facebook account** + **Meta Business portfolio** | Owns the WhatsApp Business Account (WABA) | business.facebook.com |
| **Meta Developer account** | Creates the app that talks to the WhatsApp Cloud API | developers.facebook.com |
| **A phone number for the bot** (optional for a first test) | Meta gives you a free *test number*. For a real demo where anyone can scan, use a number that is **not** registered on WhatsApp or the WhatsApp Business app (or delete that account first) | Any SIM or virtual number that can receive an SMS or voice OTP |
| **ngrok** or **cloudflared** (Path A) | Public HTTPS URL for Meta's webhook | `brew install ngrok` (free account and authtoken) or `brew install cloudflared` |
| **Razorpay account** (optional) | "Pay now" links. **Test mode** is enough for a demo | dashboard.razorpay.com |
| **Anthropic API key** (optional) | AI understanding of free text such as "day after tomorrow evening" | console.anthropic.com |
| **Vercel account** + **Neon or Supabase** (Path B) | Hosting | vercel.com |

---

## 2. Run the app locally (no WhatsApp yet)

```bash
cd appointment-scheduling-system

# Database: Postgres 17 with roles app_owner / app_rw / app_purge (infra/postgres/init.sql)
docker compose up -d db

# Backend
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000      # leave running → http://localhost:8000/docs
```

In a second terminal (from `backend/`), create the people and the clinic. Passwords are prompted.

```bash
uv run python -m app.bootstrap.cli create-superadmin --email you@example.com --name "You"
uv run python -m app.bootstrap.cli create-tenant --name "Sunrise Clinic" --slug sunrise-clinic --module appointments
uv run python -m app.bootstrap.cli add-member --tenant sunrise-clinic --email admin@example.com --name "Clinic Admin" --role admin
# Optional extras: --role doctor / reception staff, same command
```

> `create-tenant` defaults to `--timezone Asia/Kolkata`. Pass another IANA zone if needed.

In a third terminal, start the dashboard:

```bash
cd frontend
cp .env.example .env.local        # leave VITE_API_BASE_URL empty
npm install
npm run dev                       # → http://localhost:5173, sign in as admin@example.com
```

**Sanity check without Meta.** Keep `WHATSAPP_SENDER=recording` and chat with the bot in the terminal:

```bash
uv run python -m app.bootstrap.cli connect-whatsapp --tenant sunrise-clinic --phone-number-id 100000000000001 --display-phone "+91 98765 43210"
uv run python -m app.bootstrap.cli simulate --tenant sunrise-clinic
```

The bot needs doctors and opening hours before it can offer slots. Set those up first (section 5).

> **Want a full dashboard to show?** `uv run python -m app.bootstrap.cli seed-demo` creates a separate
> clinic, "Sunrise Clinic (Demo)", full of realistic data (logins `admin@sunrise.demo`, etc.). It only
> works with `ENVIRONMENT=local`. Its WhatsApp number is fake (`100000000000777`), so use your
> own tenant (`sunrise-clinic`) for the live QR part.

---

## 3. Meta / WhatsApp Cloud API setup

Meta renames menu items often. The names below were correct when this guide was written; if one has moved, search the developer dashboard for it.

### 3.1 Create the app

1. Go to **developers.facebook.com → My Apps → Create App**.
2. Use case: **"Connect with customers through WhatsApp"** (older UI: type **Business**, then add the **WhatsApp** product).
3. Pick (or create) your **Business portfolio**. Meta creates a WhatsApp Business Account (WABA) and a **free test phone number**.

### 3.2 Note the IDs

In the app, open **WhatsApp → API Setup** (or "Quickstart → API Setup"):

| Value | What it is | Used for |
|---|---|---|
| **Phone number ID** | Long number, e.g. `1098765432101234`. **Not** the phone number itself | `cli connect-whatsapp --phone-number-id` and `set-credentials` |
| **WhatsApp Business Account ID** | The WABA | Subscribing the app (3.6) and QR codes (section 7) |
| **Temporary access token** | Expires after **24 hours** | Quick first test only. Replace it in 3.4 |

### 3.3 Test number: add recipients

The test number can only message up to **5 verified phone numbers**. Under **API Setup → To**,
add your own WhatsApp number (and those of any demo volunteers) and enter the OTP each one receives.

> For a demo where the **audience** scans the QR code with their own phones, you need a **real number** (3.7).
> Otherwise the bot can't reply to anyone who isn't on the list.

### 3.4 Permanent access token (System User)

The bot must keep working after 24 hours, so create a token that doesn't expire:

1. **business.facebook.com → Settings → Users → System users → Add**. Give it a name like `clinic-bot` and the role **Admin**.
2. **Assign assets**: add your **App** (full control) and your **WhatsApp account** (full control).
3. **Generate new token**: choose your app, set expiry to **Never**, and tick the permissions
   **`whatsapp_business_messaging`** and **`whatsapp_business_management`**.
4. Copy the token. You will paste it into `cli set-credentials` (it is stored encrypted, never in `.env`).

### 3.5 App secret and verify token

- **App secret:** in the app, open **App settings → Basic → App secret → Show**. This becomes `META_APP_SECRET`.
  The backend uses it to check the `X-Hub-Signature-256` header on every webhook.
- **Verify token:** any random string you choose. It becomes `META_VERIFY_TOKEN`, and you type the same value into Meta in section 4.

### 3.6 Subscribe the app to the WABA (only needed if webhooks don't arrive)

The dashboard flow usually does this for you. If messages never reach your webhook, run:

```bash
curl -X POST "https://graph.facebook.com/v23.0/<WABA_ID>/subscribed_apps" \
  -H "Authorization: Bearer <PERMANENT_TOKEN>"
```

### 3.7 Use a real phone number (for audience demos and go-live)

1. **WhatsApp → API Setup → Add phone number** (or WhatsApp Manager → Phone numbers → Add).
2. Enter the **display name** (the clinic name; Meta reviews it), category **Medical & health**, and the number. Verify it with an SMS or voice OTP.
3. Set a **two-step verification PIN** if asked.
4. Note this number's **Phone number ID**. It is a different ID from the test number's.
5. **Business verification** (Business settings → Security centre) raises your sending limits. An unverified business can still start a limited number of conversations a day, which is enough for a demo.
6. **App mode:** to receive webhooks for real users, switch the app to **Live**. This needs a Privacy Policy URL under App settings → Basic.
7. **Billing:** add a payment method in WhatsApp Manager. Replies within 24 h of the patient's message are free service conversations. Reminders sent with templates are paid.

---

## 4. Connect WhatsApp to the app (Path A: laptop)

### 4.1 Generate secrets

```bash
cd backend
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # CREDENTIALS_KEY
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"                                 # META_VERIFY_TOKEN
```

> Keep `CREDENTIALS_KEY` safe and never change it. It encrypts stored access tokens and Razorpay
> secrets, and if it changes they can no longer be read, so you would have to enter them again.

### 4.2 Edit `backend/.env`

```dotenv
ENVIRONMENT=local
WHATSAPP_SENDER=meta                 # real messages now. `cli simulate` refuses to run in this mode
META_GRAPH_API_VERSION=v23.0
META_APP_SECRET=<app secret from 3.5>
META_VERIFY_TOKEN=<random string from 4.1>
CREDENTIALS_KEY=<Fernet key from 4.1>
```

Restart uvicorn after editing `.env`.

### 4.3 Open a public tunnel

```bash
ngrok http 8000
# or: cloudflared tunnel --url http://localhost:8000
```

Copy the `https://….ngrok-free.app` URL. On ngrok's free plan this URL changes every restart; if
it does, update the callback URL in 4.4.

### 4.4 Register the webhook in Meta

In the app, open **WhatsApp → Configuration → Webhook → Edit**:

| Field | Value |
|---|---|
| Callback URL | `https://<your-tunnel>/webhooks/whatsapp` |
| Verify token | Exactly your `META_VERIFY_TOKEN` |

Click **Verify and save**. Meta calls `GET /webhooks/whatsapp`; the app returns 200 only if the token matches.
Then, under **Webhook fields**, **Subscribe** to **`messages`**. This one field carries incoming messages, delivery statuses and WhatsApp Pay statuses.

### 4.5 Tell the app which number belongs to which clinic

```bash
# If you ran the fake connect-whatsapp from section 2, this adds the real number alongside it.
uv run python -m app.bootstrap.cli connect-whatsapp --tenant sunrise-clinic \
    --phone-number-id <PHONE_NUMBER_ID> --display-phone "+91 98xxx xxxxx"

uv run python -m app.bootstrap.cli set-credentials --phone-number-id <PHONE_NUMBER_ID>
# paste the permanent token from 3.4 (input hidden; stored encrypted with CREDENTIALS_KEY)
```

### 4.6 Start the background-job loop (required)

Confirmations after staff approve a request, payment messages, request expiry, reminders and
retention all run as background jobs. In production an external scheduler (cron-job.org) triggers them every minute (10.5).
On your laptop, keep this running in its own terminal:

```bash
cd backend
while true; do uv run python -m app.bootstrap.cli tick; sleep 30; done
```

### 4.7 First real message

From a phone on the recipient list (3.3), send **"Hi"** to the bot's number. You should see:

- the bot's reply (a menu with buttons) on the phone,
- a `POST /webhooks/whatsapp 200` line in the uvicorn log,
- the conversation in the dashboard's **Inbox**, updating live.

If nothing happens, see section 12.

---

## 5. Clinic setup in the dashboard

Sign in at http://localhost:5173 as the clinic admin and open **Settings**.

| Tab | What to set | Needed for the demo? |
|---|---|---|
| **Locations** | Branch name, address, time zone | Yes, at least one |
| **Doctors** | Doctor name, location, **weekly hours** (HoursEditor) | **Yes.** No doctors or hours means no slots to offer |
| **Booking rules** | • *Staff approve every booking* (on: the request waits on **Requests**; off: booked instantly)<br>• *Ask for reason for visit*<br>• *AI understanding* (section 9)<br>• Request expiry hours, change cut-off hours, minimum notice (minutes), booking horizon (days)<br>• **Reminder hours**, e.g. `24, 2`<br>• **Consultation fee (₹)**: 0 turns payments off<br>• Retention days (closed / inactive open cases) | Yes. For a quick demo, set minimum notice low (e.g. 30 min) so slots later today appear |
| **Payments** | Methods: WhatsApp Pay / Razorpay link / Pay at clinic. Patients are offered the first enabled one, in that order | Optional (section 8) |
| **WhatsApp templates** | Approved template name for each slot | Only for messages sent >24 h after the patient's last message (section 6) |
| **Users** | Add receptionists and doctors | Optional |

---

## 6. WhatsApp message templates (reminders and late updates)

WhatsApp only lets a business send free-form messages within **24 hours** of the patient's last message.
After that, only Meta-approved **templates** can be sent. Replies during a live demo are always
inside the window, so templates matter for **reminders** and for **approvals that happen the next day**.

Create these in **WhatsApp Manager → Message templates → Create template** (category **Utility**, language English).
Add the variables and the **quick-reply** buttons **in this exact order**:

| Slot (Settings → WhatsApp templates) | Body example | Variables | Quick-reply buttons |
|---|---|---|---|
| `appointments.reminder` | `Reminder: {{1}} has an appointment with {{2}} on {{3}} (ref {{4}}).` | patient name, doctor, date & time, reference | Confirm, Reschedule, Cancel |
| `appointments.reminder_pay` | `Reminder: {{1}} has an appointment with {{2}} on {{3}} (ref {{4}}). {{5}} is due - pay now or at the clinic.` | + amount due | Confirm, Reschedule, Cancel, Pay now |
| `appointments.payment_due` | `The consultation fee of {{1}} for appointment {{2}} is due.` | amount, reference | Pay now |
| `appointments.update` | `Update about your appointment: {{1}}` | message | none |

After Meta approves each one (minutes to hours), enter its **template name** in the dashboard under
**Settings → WhatsApp templates**. Until then, those messages are skipped for patients outside the 24 h window.

---

## 7. The QR code (scan → WhatsApp opens with "Hi")

The app doesn't generate QR codes itself. The bot treats **any first message** as a greeting, so any
QR code that opens a chat with the clinic's number works. Pick one of these options:

**Option 1: Meta's official QR code (recommended).** It shows the clinic's verified name and can be managed in WhatsApp Manager.

```bash
curl -X POST "https://graph.facebook.com/v23.0/<PHONE_NUMBER_ID>/message_qrdls" \
  -H "Authorization: Bearer <PERMANENT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"prefilled_message": "Hi, I want to book an appointment", "generate_qr_image": "PNG"}'
```

The response includes `deep_link_url` (`https://wa.me/message/…`) and `qr_image_url`. Download the PNG
and print it or put it on a slide. You can also create and download these in **WhatsApp Manager →
Phone numbers → (your number) → Message links / QR codes**.

**Option 2: a plain `wa.me` link.** Paste this into any QR generator:

```
https://wa.me/91XXXXXXXXXX?text=Hi%2C%20I%20want%20to%20book%20an%20appointment
```

Use the full number with country code and no `+`, spaces or dashes.

**One QR code per branch:** generate one per location with a different pre-filled message (e.g. "Hi – Andheri branch").

> With the **test number**, only phones on the recipient list (3.3) get replies. For an audience demo,
> use a real number (3.7).

---

## 8. Payments

Enable methods in **Settings → Payments** and set the fee in **Settings → Booking rules**.
When an appointment is confirmed, the patient gets a **Pay now** message.

### Razorpay links (easiest to demo; use Test mode)

1. In the Razorpay dashboard, switch to **Test mode**, open **Account & Settings → API keys → Generate**, and copy the **Key ID** (`rzp_test_…`) and **Key secret**.
2. In the app, open **Settings → Payments**: tick *Razorpay*, then enter the key id, key secret and a **webhook secret** you make up. The secrets are stored encrypted, which needs `CREDENTIALS_KEY`. The screen then shows the webhook path, `/webhooks/razorpay/<tenant_id>`.
3. In Razorpay, open **Webhooks → Add new webhook**:
   - URL: `https://<your-tunnel-or-api-domain>/webhooks/razorpay/<tenant_id>`
   - Secret: the same webhook secret
   - Events: **`payment_link.paid`**, **`payment_link.expired`**, **`payment_link.cancelled`**, **`refund.processed`**
4. Demo: tap **Pay now** on WhatsApp and pay with a Razorpay test card or test UPI (`success@razorpay`). The payment turns *Paid* on the **Payments** page and the patient gets a receipt.

### WhatsApp Pay (India; needs Meta approval)

Link the clinic's payment gateway account in **WhatsApp Manager → Payment configurations**, then enter the
**configuration name** in Settings → Payments. Statuses arrive on the same `/webhooks/whatsapp` webhook.
Approval can take a while, so for a demo use Razorpay test mode or **Pay at clinic**.

### Pay at clinic

No setup needed. The bot says the amount is payable at the clinic, and staff click **Mark as paid**.

---

## 9. AI understanding (optional)

1. In `backend/.env`, set:
   ```dotenv
   LLM_PROVIDER=anthropic
   ANTHROPIC_API_KEY=sk-ant-...
   # LLM_MODEL=claude-haiku-5-5   (default)
   ```
2. Restart the backend.
3. Tick **Settings → Booking rules → Let AI read free-typed dates…** for the clinic.

Only the message text is sent, never names or phone numbers. If the AI fails, the bot simply asks again.

---

## 10. Production on Vercel (Path B)

### 10.1 Database (Neon or Supabase, region `ap-south-1` / Mumbai)

1. Create the project and a database named `wa_platform`. If you use a different name, change it in `init.sql`.
2. In the provider's SQL console, run [infra/postgres/init.sql](../infra/postgres/init.sql). **Change the three passwords first.**
   **On Supabase:** use the built-in `postgres` database instead (replace `wa_platform` with `postgres`, drop the
   `\connect` line, and add `GRANT app_owner TO postgres;` before `ALTER SCHEMA`). Connect through the pooler
   `aws-0-<region>.pooler.supabase.com` with user `<role>.<project-ref>`: port **6543** (transaction) for the pooled
   URLs, and port **5432** (session) for the migration URL, because the direct `db.<ref>.supabase.co` host is IPv6-only.
3. Build three connection strings (use the `postgresql+psycopg://` prefix):

| Env var | Role | Connection type |
|---|---|---|
| `DATABASE_URL` | `app_rw` | **Pooled** |
| `DATABASE_PURGE_URL` | `app_purge` | **Pooled** |
| `DATABASE_MIGRATION_URL` | `app_owner` | **Direct** (non-pooled) |

4. Run migrations from your laptop against production. CI only migrates its own test database.
   ```bash
   cd backend
   DATABASE_MIGRATION_URL='postgresql+psycopg://app_owner:...@<direct-host>/wa_platform?sslmode=require' uv run alembic upgrade head
   ```
5. Create the super-admin, tenant and admin with the same CLI commands as section 2, prefixed with
   `DATABASE_URL='<pooled app_rw url>'`. Then run `connect-whatsapp` and `set-credentials`; those also need
   `CREDENTIALS_KEY` set to the **same** value as in Vercel.

### 10.2 API project (`backend/`)

1. In Vercel, **Add New → Project →** import the repo, then set **Root Directory = `backend`**.
2. Region `bom1` is already set in `backend/vercel.json`. There's no Vercel cron (Hobby only allows daily); see 10.5.
3. Environment variables:

```dotenv
ENVIRONMENT=production
LOG_LEVEL=INFO
DATABASE_URL=...            # pooled, app_rw
DATABASE_PURGE_URL=...      # pooled, app_purge
DATABASE_MIGRATION_URL=...  # direct, app_owner
JWT_SECRET=<token_urlsafe(48)>
CRON_SECRET=<token_urlsafe(48)>       # the scheduler sends it as "Authorization: Bearer ..."
CORS_ORIGINS=["https://<web-project>.vercel.app"]
WHATSAPP_SENDER=meta
META_GRAPH_API_VERSION=v23.0
META_APP_SECRET=...
META_VERIFY_TOKEN=...
CREDENTIALS_KEY=...                   # same key you used with the CLI
LLM_PROVIDER=none                     # or anthropic + ANTHROPIC_API_KEY
```

The app **refuses to start** in production if `JWT_SECRET` or `CRON_SECRET` still have their default values, or if
`WHATSAPP_SENDER=meta` is set without `META_APP_SECRET` and `CREDENTIALS_KEY`. Webhook signatures are always required outside local.

### 10.3 Dashboard project (`frontend/`)

1. In [frontend/vercel.json](../frontend/vercel.json), replace `REPLACE-WITH-API-PROJECT` with your API project's domain, then commit.
2. In Vercel, add a new project from the same repo with **Root Directory = `frontend`**. Leave `VITE_API_BASE_URL` empty; the rewrite keeps everything on one origin, so login cookies work.

### 10.4 Point Meta and Razorpay at production

- Meta webhook callback: `https://<api-project>.vercel.app/webhooks/whatsapp`
- Razorpay webhook: `https://<api-project>.vercel.app/webhooks/razorpay/<tenant_id>`
- Health check: open `https://<api-project>.vercel.app/docs`, and see **System status** in the dashboard.

### 10.5 Background jobs tick (cron-job.org)

Vercel Hobby only runs crons once a day, so a free external scheduler calls the tick endpoint instead.

1. Sign up at [cron-job.org](https://cron-job.org) and click **Create cronjob**.
2. URL: `https://<api-project>.vercel.app/internal/jobs/tick`. Schedule: **every minute**.
3. Under **Advanced → Headers**, add `Authorization` = `Bearer <CRON_SECRET>`, using the same value as in Vercel.
4. Save, then check the job's history: each run should return **200** with JSON counts. A **401** means the secret doesn't match.

The tick also keeps the Supabase free project active, so it doesn't pause after a week without traffic.

---

## 11. Demo script (about 10 minutes)

**Before the demo:**
- Backend, dashboard, tunnel and **tick loop** are all running. (On Vercel, the cron replaces the tick loop.)
- At least one doctor has hours **today**, and minimum notice is low.
- The QR code is on screen or printed. The dashboard is open on the projector, on the **Requests** page.
- Send "Hi" once yourself to check that everything works.

**On stage:**
1. **Scan:** a volunteer scans the QR code, WhatsApp opens with the pre-filled message, they tap send, and the bot replies with the menu.
2. **Book:** they tap **Book appointment**, then pick a doctor, day and slot, give the patient name (and reason, if that rule is on), and confirm. The bot sends a reference such as `APT-7K3Q`.
3. **Live dashboard:** the request appears on **Requests** without a page refresh.
4. **Approve:** click Approve. Within one tick, the patient gets "Confirmed" plus **Pay now** (if a fee is set).
5. **Pay:** tap Pay now and pay with a Razorpay test payment. **Payments** shows *Paid* and WhatsApp shows a receipt.
6. **Reschedule / cancel:** the patient types "Hi" again and the menu shows their appointment, with Reschedule and Cancel.
7. **Human handover:** the patient asks to talk to staff. The chat appears in **Inbox**, where staff take it over and reply from the dashboard.
8. **Privacy:** the patient types `DELETE MY DATA`, and staff approve the request on the **Privacy** page.
9. (Optional) **AI:** type "day after tomorrow evening" when asked for a day.
10. Show **reminders**: Booking rules → reminder hours (they use the templates from section 6).

---

## 12. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Meta says **"callback URL or verify token couldn't be validated"** | The tunnel isn't running, the URL doesn't end in `/webhooks/whatsapp`, or the token doesn't match `META_VERIFY_TOKEN` exactly. Restart uvicorn after editing `.env` |
| Webhook verified, but **no POST arrives** when you message | You didn't subscribe to the `messages` field (4.4), the app isn't subscribed to the WABA (3.6), or the app is in Dev mode with a real number (3.7.6) |
| uvicorn shows **401 Bad signature** | Wrong `META_APP_SECRET`. Copy it again from App settings → Basic |
| **503 "Webhook secret not configured"** | You're running outside local without `META_APP_SECRET` |
| Webhook returns 200 but **the bot doesn't reply** | Check that `connect-whatsapp` used the **phone number ID**, not the phone number. Check `set-credentials` ran with a valid permanent token, and that `WHATSAPP_SENDER=meta` |
| Meta error **131030 "recipient not in allowed list"** | Test number: add the recipient (3.3), or use a real number |
| Meta error **190 / token expired** | You used the 24 h temporary token. Make a System User token (3.4) and run `set-credentials` again |
| Meta error **131047 / re-engagement** | More than 24 h since the patient's last message. Map a template (section 6) |
| Bot says **no slots available** | No doctor hours today, minimum notice too high, or the booking horizon is too short |
| Patient gets **no confirmation after Approve** | The tick loop isn't running (4.6), or the cron-job.org job is failing (10.5) |
| Razorpay **paid, but app still shows pending** | Wrong webhook URL or tenant id, wrong secret, or the `payment_link.paid` event isn't ticked |
| Saving secrets fails / **can't decrypt** credentials | `CREDENTIALS_KEY` is empty or was changed. Set it back to the original key, or enter the secrets again |
| `cli simulate` refuses to run | It only works with `WHATSAPP_SENDER=recording`, so it can never message real people |
| App won't start on Vercel | Read the error: default `JWT_SECRET`/`CRON_SECRET`, or meta mode without its secrets (10.2) |

---

## 13. Environment variable reference (`backend/.env`)

| Variable | Required | Default | Notes |
|---|---|---|---|
| `ENVIRONMENT` | yes | `local` | `local` / `test` / `preview` / `production`. Non-local enforces secrets and webhook signatures |
| `LOG_LEVEL` | no | `INFO` | |
| `DATABASE_URL` | yes | local `app_rw` | Pooled in production |
| `DATABASE_PURGE_URL` | yes | local `app_purge` | Pooled in production; retention job |
| `DATABASE_MIGRATION_URL` | yes | local `app_owner` | **Direct** in production; Alembic |
| `JWT_SECRET` | prod | dev default | `secrets.token_urlsafe(48)` |
| `CRON_SECRET` | prod | dev default | Bearer token for `/internal/jobs/tick` |
| `ACCESS_TOKEN_MINUTES` / `REFRESH_TOKEN_DAYS` | no | 15 / 14 | Dashboard sessions |
| `CORS_ORIGINS` | no | `["http://localhost:5173"]` | JSON list |
| `WHATSAPP_SENDER` | yes | `recording` | `meta` sends real messages |
| `META_GRAPH_API_VERSION` | no | `v23.0` | |
| `META_APP_SECRET` | with meta | empty | Webhook signature check |
| `META_VERIFY_TOKEN` | with meta | `local-verify-token` | Webhook subscription check |
| `CREDENTIALS_KEY` | with meta / Razorpay | empty | Fernet key; encrypts tokens and secrets. **Never change it** |
| `LLM_PROVIDER` | no | `none` | `anthropic` turns AI on |
| `ANTHROPIC_API_KEY` | with anthropic | empty | |
| `LLM_MODEL` | no | `claude-haiku-5-5` | |
| `TEST_DATABASE_URL` | tests only | not set | Enables DB tests |

Frontend (`frontend/.env.local`): `VITE_API_BASE_URL`, left empty. For local dev with the API on another port, run `API_PROXY_TARGET=http://localhost:8010 npm run dev`.

**Where each secret lives:**
- `.env` / Vercel env vars: app-wide secrets.
- Database, encrypted: per-number Meta access tokens (`cli set-credentials`) and per-clinic Razorpay key secret and webhook secret (dashboard).
- Never in git.
