# PRD: WhatsApp Business Automation Platform

**First module: Appointment Scheduling**

| | |
|---|---|
| **Status** | Draft v0.3 |
| **Date** | 2026-10-09 |
| **Owner** | Niharika |
| **Changes since v0.1** | v0.2: Turned into a multi-tenant, multi-purpose platform. Added conversation routing based on the sender's state, staff approval of requests, a staff inbox, and reminders and payments over WhatsApp. v0.3: Added **Cases** (treatment episodes) and **data retention and deletion** (§7.10). |
| **Next document** | `docs/ARCHITECTURE.md` (SOLID, layered design) |

---

## 1. Overview

This is a **multi-tenant platform for automating WhatsApp Business conversations**. Businesses ("tenants") connect their WhatsApp Business number. The platform then runs automation **modules** on that number.

**Appointment Scheduling** is the first module, built for clinics:

- A patient scans the clinic's QR code, which opens a WhatsApp chat.
- The patient books, reschedules, cancels and pays through that chat.
- Clinic staff approve and reply to requests from a web dashboard.
- Doctors see their appointments, booking details and change history on the same dashboard.

Later modules can include order updates, lead capture, feedback surveys, broadcast campaigns and support tickets. They will reuse the same platform core: tenants, contacts, conversations, messaging, templates, payments, the staff inbox, users and roles, and audit logging.

The appointment module holds patient registration details, booking information, payments and appointment history. It does **not** hold clinical records (see §4).

## 2. Problem

- Booking by phone takes up front-desk time and often fails outside working hours.
- When a patient reschedules, they are usually asked for their details all over again.
- Rescheduling is often done by cancelling and rebooking. This creates duplicate records and loses the history.
- Doctors cannot easily see why a patient is coming in, or what has changed.
- Collecting fees in advance and reducing no-shows both need manual follow-up.
- Every new WhatsApp automation a business wants is usually built from scratch. A shared platform core avoids that.

## 3. Goals

| # | Goal | How we measure it |
|---|---|---|
| G1 | Patients can book, reschedule, cancel and pay entirely over WhatsApp | ≥ 80% of requests finish without staff typing a message |
| G2 | Returning contacts are never asked for details we already hold | 0 repeated questions for stored fields, checked by conversation tests |
| G3 | Rescheduling keeps the same appointment and records every change | 0 duplicate patients or appointments created by a reschedule |
| G4 | Staff can deal with every pending request from one dashboard | Median time for staff to respond to a request ≤ 15 minutes during working hours |
| G5 | Fewer missed appointments and more fees collected in advance | No-show rate down ≥ 30% and ≥ 50% of fees paid in advance (compared with the clinic's numbers before launch) |
| G6 | A new module can be added without changing the platform core | The second module ships with no changes to core packages beyond extension points |
| G7 | Tenants are completely isolated from each other | 0 cases of one tenant's data reaching another, checked by automated tests on every endpoint |

## 4. Non-goals (v1)

- Diagnoses, prescriptions, clinical notes, lab results or any electronic medical record features
- Insurance claims, invoicing or accounting. Payments cover **consultation and booking fees only.**
- Video consultations
- A patient-facing mobile app or web portal (WhatsApp is the only end-user channel)
- Channels other than WhatsApp. The design leaves room to add them later.
- Modules other than Appointment Scheduling. The platform is ready for them, but none are built in v1.

## 5. Users and roles

| Role | Scope | Main needs |
|---|---|---|
| **Platform super-admin** | Whole platform | Add tenants, connect WhatsApp numbers, turn modules on or off, monitor health |
| **Tenant admin** | One tenant | Configure the business, users, modules, templates, payments, doctors, availability and booking fields |
| **Staff / receptionist** | One tenant | Approve, decline or suggest another time for requests; reply to patients in the inbox; manage appointments |
| **Doctor** | One tenant, own appointments | See today's and upcoming appointments, reasons for visit and history; mark appointments completed or no-show |
| **Contact / patient** | WhatsApp end user | Book, reschedule, cancel, pay and talk to a person, without repeating themselves |
| **System (bot)** | One tenant | Uses the same application services and business rules as the dashboard |

---

## 6. Platform core requirements

The platform core is shared by every module.

### 6.1 Tenancy

| ID | Requirement |
|---|---|
| PL-1.1 | Each tenant has its own WhatsApp Business number(s), users, settings, templates, payment account and data. |
| PL-1.2 | Incoming webhooks are matched to a tenant using the WhatsApp `phone_number_id`. |
| PL-1.3 | Every tenant-owned table has a `tenant_id` column. All data access is filtered by tenant automatically, and the database adds a second check (Postgres row-level security). |
| PL-1.4 | Modules are turned on per tenant, and each tenant can have its own module settings. |
| PL-1.5 | Each tenant can have more than one **location** (for example clinic branches). Each location has its own QR code, address and time zone. |

### 6.2 Contacts and identity

| ID | Requirement |
|---|---|
| PL-2.1 | A **Contact** is a WhatsApp number within one tenant. It is unique on `(tenant_id, phone_e164)`. If the same person messages two tenants, they become two separate, isolated contacts. |
| PL-2.2 | Modules attach their own profiles to a contact. In the appointment module, **one contact can be linked to several patients** (for example a parent booking for children or older relatives). |
| PL-2.3 | The WhatsApp sender number is taken as verified. No OTP is needed. |
| PL-2.4 | The platform records consent on first contact and honours opt-out. Replying `STOP` stops all reminders and promotional messages. Replies to messages the contact sends are not affected. |

### 6.3 Conversation engine and routing

| ID | Requirement |
|---|---|
| PL-3.1 | Each contact has at most one **conversation session** at a time. It holds the active module, the current step of the flow, and data collected so far. Sessions expire after 24 hours of no activity. |
| PL-3.2 | Every incoming message is handled in this order: dedupe by WhatsApp message ID → resolve tenant → resolve contact → check for an active staff handover (if there is one, send the message to the inbox and stop) → check for a global command (`MENU`, `STOP`, `AGENT`, `RESTART`) → continue the active flow, or **route** a new conversation (§7.1). |
| PL-3.3 | Flows are made up of small, separate steps. Each step validates the reply, saves it, and decides the next step. Adding a flow or a step does not require changing the engine. |
| PL-3.4 | The bot uses WhatsApp **interactive messages** (reply buttons and list menus) wherever possible, and falls back to numbered text menus. |
| PL-3.5 | At any point, the contact can type `MENU` to go back to the main menu, or `AGENT` / "talk to someone" to ask for a person. |

### 6.4 Messaging and templates

| ID | Requirement |
|---|---|
| PL-4.1 | All sending goes through a single `MessagingGateway` interface. Meta Cloud API is the first implementation. |
| PL-4.2 | Messages sent **outside the 24-hour customer-service window** (reminders, approval results, payment requests) must use **Meta-approved templates**. Tenants map each platform event to one of their approved templates. |
| PL-4.3 | Messages are sent from a queue and retried with back-off. Delivery and read statuses from webhooks are saved for each message. |
| PL-4.4 | All incoming and outgoing messages are saved in the conversation log, which the staff inbox displays. |

### 6.5 Staff inbox and human handover

| ID | Requirement |
|---|---|
| PL-5.1 | The dashboard has a **shared inbox**, a list of conversations with the newest messages and unread counts. |
| PL-5.2 | Staff can **take over** a conversation. While they have it, the bot is paused for that contact and staff replies go out over WhatsApp. When staff **hand it back**, the bot carries on. |
| PL-5.3 | A handover starts when the contact asks for a person (`AGENT`), when the bot fails to understand the same step 3 times in a row, or when staff choose to take over. |
| PL-5.4 | Outside the 24-hour window, staff can only send templates. The inbox shows this clearly. |

### 6.6 Payments

| ID | Requirement |
|---|---|
| PL-6.1 | There are **three payment methods**, and each tenant **turns on any combination** of them in settings. **(A) WhatsApp Payments**: the patient gets a **Review and pay** message and pays inside WhatsApp, for example with UPI. The clinic links its payment account (for example Razorpay) once in WhatsApp Business Manager, and the payment result arrives on our WhatsApp webhook. **(B) Razorpay payment link**: the bot sends a Razorpay link in the chat, and the result arrives on our Razorpay webhook. **(C) Pay at clinic**: the patient pays by cash or UPI at the counter, and staff record it with **Mark as paid**. A and B go through one `PaymentGateway` interface, and C is a gateway that sends nothing. |
| PL-6.2 | Each tenant connects its own payment account. For A this is done in WhatsApp Business Manager. For B the tenant enters its Razorpay API keys in settings, which are stored encrypted. C needs no setup. Payments go directly to the tenant. |
| PL-6.3 | A payment request has an amount, currency, purpose, link to the module record (for example an appointment), status, expiry time and method (`whatsapp_pay`, `razorpay_link` or `at_clinic`). |
| PL-6.4 | Payment status is updated **only from signed webhooks** (WhatsApp or Razorpay), or by staff using **Mark as paid** (for cash or UPI paid at the clinic, or if the status update never arrives). It is never updated just because the patient says they have paid. |
| PL-6.5 | Payment statuses: `PENDING` → `PAID` / `FAILED` / `EXPIRED`, and `PAID` → `REFUNDED`. A **Pay at clinic** request that is still `PENDING` when its appointment ends as Cancelled, Declined, Expired or No-show becomes `EXPIRED` automatically, so it never blocks the retention purge (RT-6). Each change is saved as a history event. Refunds: with option B, staff can **refund from the dashboard** through the Razorpay API. With option A, the clinic refunds outside the system and staff record it with **Mark as refunded**. |
| PL-6.6 | WhatsApp reminders can include a **Pay now** button. It opens the in-chat payment (A) or the Razorpay link (B), so the patient can pay straight from the reminder. For Pay at clinic (C), the reminder instead says *"₹500 payable at the clinic"*. |

### 6.7 Scheduled jobs and reminders

| ID | Requirement |
|---|---|
| PL-7.1 | A job scheduler runs time-based actions: reminders, request expiry, payment request expiry and session clean-up. |
| PL-7.2 | Each tenant can set its own reminder times (default: 24 hours and 2 hours before). |
| PL-7.3 | Jobs are idempotent: if a job runs again, the same reminder is not sent twice. |

### 6.8 Users, roles and audit

| ID | Requirement |
|---|---|
| PL-8.1 | Dashboard users sign in with email and password, which issues short-lived access tokens and refresh tokens. A user belongs to one or more tenants and has a role in each. |
| PL-8.2 | Permissions are checked per action (for example `appointment.approve`, `inbox.reply`, `settings.manage`), not just per role. |
| PL-8.3 | Every read or change of personal data is written to an **audit log** recording who, what, when and from where. |

---

## 7. Appointment module requirements

### 7.1 Greeting routing (what happens when someone says "Hi")

When a contact sends a greeting (`hi`, `hello`, `hey`, `namaste` and so on, configurable per tenant), the QR code's pre-filled message, or any message with no active session, the router looks at the contact's current state and chooses a starting point.

| # | Contact state | What the bot does |
|---|---|---|
| R1 | **New number** (no contact record) | Welcome them as a new patient → ask for consent → collect patient details → booking flow (§7.2) |
| R2 | Known contact, **an appointment is active** (Requested, Confirmed or Rescheduled, still upcoming) | Greet them by name and show it: *"Your appointment with Dr. Amit is Fri 12 Oct, 3:00 PM (APT-7K3Q)"*. Then show the **main menu**: View · Reschedule · Cancel · Pay (if unpaid) · Book another · Talk to staff |
| R3 | Known contact, **no active appointments** (all past ones are Completed, Cancelled, No-show, Declined or Expired, or their case has been closed) | *"Welcome back, Rahul!"* Then: Book new appointment (**stored details reused**, only missing fields asked; a **new case** is started if the previous one is closed) · View past appointments · Talk to staff. If the patient's data has already been deleted (§7.10), they are treated as **R1**, a new patient. |
| R4 | Known contact with **several patients** linked | Ask *"Who is this for?"* and list the patients plus **"Someone new"**, then continue with R2 or R3 for that patient. "Someone new" collects details for a new patient profile under the same number. |
| R5 | A **request is waiting for staff approval** | *"Your request for Fri 12 Oct, 3:00 PM is waiting for the clinic to confirm. We'll message you here."* Menu: Change request · Withdraw request · Talk to staff |
| R6 | A **payment is due** (pending payment request) | Show a **Pay now** button first, then the usual menu |
| R7 | A **flow was interrupted** (session still open) | *"You were booking with Dr. Amit. Continue or start over?"* |
| R8 | A **staff member has taken over** the chat | The message goes to the inbox with no bot reply. The contact sees nothing automated. |
| R9 | The contact has **opted out** (`STOP`) | Reply to their message. Ask whether they want to receive reminders again. |
| R10 | The appointment is **today, within the cut-off** | Show the appointment and the clinic's phone number. Reschedule and cancel are not offered. |
| R11 | The message is **not a greeting** and there is no session (for example "can I come Saturday?") | Treat it as a greeting and route with R1–R10. Phase 2: an LLM works out the intent so the bot can jump straight to the right flow. |

Main menu items only appear when they make sense. For example, Pay appears only if a payment is due, and Reschedule only for appointments that can still be changed.

### 7.2 Booking (new or returning patient)

| ID | Requirement |
|---|---|
| AP-2.1 | The bot collects: patient's full name, mobile number (taken from the WhatsApp sender, never asked), location (if the tenant has more than one), doctor or specialty, preferred date and time, reason for visit (if the tenant requires it), and any **custom booking fields** set by the tenant admin (type, required/optional, order). |
| AP-2.2 | Fields already stored for the patient are **skipped**. The bot only asks for fields that are missing, newly required, or that the patient wants to change. |
| AP-2.3 | The bot offers only real free slots, based on working hours, slot length, blocked time and existing active appointments and holds. |
| AP-2.4 | The bot shows a summary (including the fee, if there is one) and asks the patient to confirm. |
| AP-2.5 | When the patient confirms, an Appointment is created with a unique ID and a short reference (for example `APT-7K3Q`), and the slot is **held**. Its starting status depends on the tenant's **approval mode**: `REQUESTED` (needs staff approval, the default) or `CONFIRMED` (auto-confirm). |
| AP-2.6 | Two patients can never hold or book the same slot, even if they confirm at the same moment. |
| AP-2.7 | If the tenant charges a fee, the bot offers the payment methods the tenant has turned on (PL-6.1). If more than one is on, it asks *"How would you like to pay?"* with options like [Pay in WhatsApp] [Pay by link] [Pay at clinic]. The tenant's **timing policy** decides when online payment is requested: **at booking** or **after approval** (the default). Choosing **Pay at clinic** sends no payment request. The appointment shows *"₹500 due at clinic"*, and staff use **Mark as paid** at the counter. |

### 7.3 Staff approval of requests

| ID | Requirement |
|---|---|
| AP-3.1 | New booking requests and reschedule requests appear in the dashboard's **Requests** queue in real time, with a notification and a count. |
| AP-3.2 | For each request, staff can choose: **Approve** → `CONFIRMED`, the patient is told, and a WhatsApp payment request is sent if needed. **Decline** (with a reason) → `DECLINED`, the slot is freed and the patient is told. **Suggest another time** → the patient gets Accept / Choose another / Cancel buttons. **Reply** → opens the inbox conversation. |
| AP-3.3 | Requests nobody responds to **expire** after a time the tenant sets (default 4 working hours). The slot is freed, the patient is told, and they are offered other times. |
| AP-3.4 | Patients can withdraw a pending request. |
| AP-3.5 | When the bot is told to auto-confirm (approval mode off), requests skip the queue. Staff still see them in the list. |

### 7.4 Rescheduling and cancelling

| ID | Requirement |
|---|---|
| AP-4.1 | The bot finds the patient's active appointments. If there is one, it confirms it with the patient. If there are several, it lists them (doctor, date, time, reference) and asks which one. If there are none, it offers to book. |
| AP-4.2 | The patient gives only what is changing: the new date and/or time, or another doctor in the same specialty if the tenant allows it. |
| AP-4.3 | The new slot must be free. If it is not, the bot suggests the 3 nearest free slots. |
| AP-4.4 | **With approval mode on:** a *reschedule request* is created and the new slot is held. **The original appointment stays valid** until staff approve. When they approve, the appointment moves to the new time and the old slot is freed. When they decline or the request expires, the hold is released and nothing else changes. |
| AP-4.5 | **With approval mode off:** the appointment is updated straight away. |
| AP-4.6 | A reschedule **updates the existing appointment**. The appointment ID and reference stay the same, the status becomes `RESCHEDULED`, and the old and new times are added to the history. |
| AP-4.7 | Cancelling sets the status to `CANCELLED`, frees the slot and records the reason. If the fee was paid, staff are shown a **refund due** task. They refund through Razorpay from the dashboard (option B), or refund outside the system and use **Mark as refunded** (option A). |
| AP-4.8 | Patients cannot reschedule or cancel inside the cut-off the tenant sets (for example 2 hours before). The bot gives the clinic's phone number instead. |
| AP-4.9 | *Worked example:* Dr. Amit, Fri 3:00 PM → Sat 5:00 PM. The bot finds the appointment from the number and confirms it with the patient. It then checks Sat 5:00 PM and creates a reschedule request. Staff approve, and the same `APT-7K3Q` now shows Sat 5:00 PM. The history shows "Fri 15:00 → Sat 17:00", with who requested it, who approved it and when. |

### 7.5 Reminders and payment

| ID | Requirement |
|---|---|
| AP-5.1 | A reminder template is sent at each reminder time the tenant has set. It has buttons: **Confirm attendance · Reschedule · Cancel**, plus **Pay now** if a payment is due. |
| AP-5.2 | Tapping a reminder button opens the matching flow straight away for that appointment, with no menu in between. |
| AP-5.3 | When the payment webhook reports success (or staff mark it as paid), a receipt is sent over WhatsApp, the appointment's payment status becomes `PAID`, and the dashboard shows it. |
| AP-5.4 | If the policy is "pay at booking" and payment hasn't arrived by the time the tenant sets, the hold is released and the patient is told. |

### 7.6 Appointment status lifecycle

```
                    ┌──── staff suggests another time ───┐
                    ▼                                    │
 [REQUESTED] ──approve──► [CONFIRMED] ──reschedule──► [RESCHEDULED] ⟲ (reschedule again)
     │  │                     │                            │
     │  ├─decline─► [DECLINED]│                            │
     │  └─timeout─► [EXPIRED] ├──cancel──► [CANCELLED] ◄───┤
     └──withdraw──► [CANCELLED]├──mark────► [COMPLETED] ◄───┤
                               └──mark────► [NO_SHOW]   ◄───┘
```

- Active statuses (they hold a slot): `REQUESTED`, `CONFIRMED`, `RESCHEDULED`.
- Final statuses: `DECLINED`, `EXPIRED`, `CANCELLED`, `COMPLETED`, `NO_SHOW`. Once all of a patient's appointments are final, the next greeting goes to **R3** (a new appointment, reusing stored details).
- Payment status is tracked **separately** from appointment status (§6.6).
- Only staff can set `COMPLETED`, `NO_SHOW` and `DECLINED`.

### 7.7 Doctor and staff dashboard

| ID | Requirement |
|---|---|
| AP-7.1 | **Requests queue** (§7.3), **Appointments** list and calendar, **Inbox** (§6.5) and **Settings**. |
| AP-7.2 | Appointments can be filtered by date range, location, doctor, appointment status and payment status, and searched by name, phone or reference. Doctors see only their own appointments by default. |
| AP-7.3 | Each appointment shows: patient name, registered phone, reference, current date and time, **original and current time** if rescheduled, reason for visit, custom fields, appointment status, payment status and amount. |
| AP-7.4 | The appointment detail page shows the full **history timeline** (created, approved, declined, rescheduled, cancelled, field changes, payment events, reminders sent) with who made each change, through which channel, and when. A link opens the WhatsApp conversation. |
| AP-7.5 | Staff can book, reschedule and cancel on a patient's behalf, using the same business rules and history as the bot. |
| AP-7.6 | Changes appear in real time (WebSocket or server-sent events). The dashboard reads from the same database as the bot. |
| AP-7.7 | Settings: locations, doctors, specialties, working hours, blocked time, slot length, booking fields, approval mode, payment policy and fees, enabled payment methods (WhatsApp Payments / Razorpay link / Pay at clinic) and their settings, payment timing, reminder times, cut-offs, greeting keywords, template mapping and users. |

### 7.8 Appointment history

| ID | Requirement |
|---|---|
| AP-8.1 | Every change to an appointment adds an **append-only event**. The application can never update or delete events. The only exception is the retention purge (§7.10), which deletes them together with the appointment they belong to. |
| AP-8.2 | Each event records: type, old and new values, who made it (`contact`, `staff:<user_id>` or `system`), channel (`whatsapp`, `dashboard` or `scheduler`) and a UTC timestamp. |
| AP-8.3 | Event types: `REQUESTED`, `CONFIRMED`, `DECLINED`, `EXPIRED`, `RESCHEDULE_REQUESTED`, `RESCHEDULED`, `RESCHEDULE_DECLINED`, `CANCELLED`, `COMPLETED`, `NO_SHOW`, `DETAILS_UPDATED`, `PAYMENT_REQUESTED`, `PAYMENT_SUCCEEDED`, `PAYMENT_FAILED`, `REFUNDED`, `REMINDER_SENT`. |
| AP-8.4 | The original booking can always be rebuilt from the first event. |

### 7.9 Data management rules

| ID | Rule |
|---|---|
| DR-1 | A patient is stored once per tenant and reused for all of their appointments. A contact (phone number) can be linked to several patients. |
| DR-2 | Every appointment belongs to exactly one tenant, patient, doctor and location. The database enforces this with foreign keys. |
| DR-3 | Rescheduling and approving never create a new patient or a new appointment. |
| DR-4 | The current state and its history event are written in the **same transaction**. |
| DR-5 | The bot asks for information only when it is missing, newly required, or being changed. |
| DR-6 | Data can only be seen by authenticated users with permission in that tenant. Isolation is enforced in the application and again in the database. |
| DR-7 | Personal data is kept only as long as the retention rules in §7.10 allow, and is then permanently deleted. |

### 7.10 Cases, data retention and deletion

**Cases.** A **Case** is one treatment episode for a patient, for example "fever, Oct 2026". It groups that episode's appointments, and staff close it when the treatment is finished.

| ID | Requirement |
|---|---|
| AP-10.1 | Every appointment belongs to exactly one case. When a patient books and has **no open case**, a new case is created. If they **have an open case**, the new appointment joins it. Staff can move an appointment to another case or start a new one from the dashboard. |
| AP-10.2 | Case statuses: `OPEN` → `CLOSED` (by staff, with an optional closing note) → `PURGED` (by the system). A `CLOSED` case can be **reopened** by staff before it is purged. |
| AP-10.3 | A case can only be closed when it has no active appointments (`REQUESTED`, `CONFIRMED` or `RESCHEDULED`). If it has any, staff must cancel or complete them first. |

**Retention rules**, run automatically every day by a scheduled job:

| ID | Rule | Deleted |
|---|---|---|
| RT-1 | A case **closed by staff** is deleted **60 days after it was closed**. | Everything belonging to the case: its appointments, history events, booking field values, change requests and reminders. **Payment records are not deleted** (see RT-7). |
| RT-2 | An **incomplete case** (still `OPEN`) is deleted **12 months after its last activity**, meaning the most recent booking, change, message or payment on the case. | Same as RT-1 |
| RT-3 | Once a patient has **no cases left**, their **patient profile** is deleted as well. | Name, custom fields, patient record |
| RT-4 | Once a contact has **no patients left** and no conversation for 60 days, the **contact** is deleted as well. | Phone number, conversation session, message log, handover records |
| RT-5 | Reopening a closed case **cancels** its pending deletion. The 60-day countdown starts again from the next time it is closed. | — |
| RT-6 | A case is **never** purged while it has an active appointment, an unsettled payment (`PENDING` or a refund in progress) or a staff **legal hold**. The purge waits until the block is cleared. | — |

| ID | Requirement |
|---|---|
| AP-10.4 | Deletion is **permanent** (hard delete), not a "deleted" flag. Backups are rotated so deleted data disappears from them within the backup retention period (for example 30 days). |
| AP-10.5 | For each purge, the system keeps only a **deletion record with no personal data**: tenant, case ID, rule applied (RT-1 or RT-2), counts of records deleted, and timestamp. This proves the deletion happened. |
| AP-10.6 | The dashboard shows each closed case's **scheduled deletion date**. A daily list shows cases due for deletion in the next 7 days, so staff can reopen a case or place a legal hold if they need to. |
| AP-10.7 | Retention periods (60 days and 12 months) are **tenant settings**, with these values as defaults. Each tenant must stay within the limits allowed by law. |
| RT-7 | **Payment records are never deleted**, whether by the retention purge or by a patient's request. When the case they belong to is deleted, each payment record is **detached** from it and becomes a standalone **payment ledger entry**. The entry keeps: tenant, receipt number, amount, currency, payment date, status, refunds, gateway and transaction reference, and the payer's name and phone as they appeared on the receipt. It does **not** keep health-related details such as reason for visit, booking fields, case notes or history. The required retention period is set by tax and accounting law and is **still to be confirmed with an accountant**. | — |

| ID | Requirement |
|---|---|
| AP-10.8 | **Patients can ask to delete their personal and health-related data.** They can type `DELETE MY DATA` (or choose *My data → Delete my data* in the menu) at any time. |
| AP-10.9 | The bot explains what will be deleted (profile, cases, appointments and history) and what will **not** be (payment records, kept for legal reasons), then asks the patient to confirm. |
| AP-10.10 | A confirmed request creates a **Deletion Request** in the dashboard. Staff must approve or reject it within the period the tenant sets (default 7 days). Rejection needs a reason, for example an upcoming appointment that must be cancelled first, or a legal hold. |
| AP-10.11 | When staff approve, the system cancels any active appointments (freeing their slots), deletes the patient's data straight away using the same purge as RT-1, keeps payment records under RT-7, and sends the patient a WhatsApp confirmation. |
| AP-10.12 | If the number has several patients linked (FR-2.3), the patient asking chooses whose data to delete, or all of them. |
| AP-10.13 | Requests and their outcomes go into the deletion record (AP-10.5), with no personal data. |

---

## 8. Example conversations

**R1: new number**
```
Patient : Hi
Bot     : Welcome to Sunrise Clinic! 👋 Looks like you're new here.
          We'll save your details to book appointments. OK?  [Yes] [No]
Patient : Yes
Bot     : Patient's full name?
Patient : Rahul Verma
Bot     : Which doctor?  [Dr. Amit – General] [Dr. Neha – Skin]
Patient : Dr. Amit
Bot     : Pick a date: [Today] [Tomorrow] [Fri 12 Oct] [Other]
Patient : Fri 12 Oct
Bot     : Free slots: [10:00] [11:30] [15:00] [16:30]
Patient : 15:00
Bot     : Reason for visit?
Patient : Fever for 3 days
Bot     : Dr. Amit · Fri 12 Oct, 3:00 PM · Rahul Verma · Fee ₹500   [Confirm] [Change]
Patient : Confirm
Bot     : Request sent ✅ (APT-7K3Q). The clinic will confirm shortly.
… staff approves on the dashboard …
Bot     : Confirmed ✅ APT-7K3Q, Fri 12 Oct 3:00 PM. Pay ₹500 now: [Pay now]
```

**R2: returning, active appointment**
```
Patient : Hello
Bot     : Hi Rahul! Your appointment: Dr. Amit, Fri 12 Oct, 3:00 PM (APT-7K3Q) – Confirmed.
          [Reschedule] [Cancel] [More ▾ → Pay · Book another · Talk to staff]
Patient : Reschedule
Bot     : New date?  …  Sat 13 Oct 5:00 PM is free. Send request?  [Yes] [No]
Patient : Yes
Bot     : Request sent. Your current time stays valid until the clinic confirms.
```

**R3: returning, previous case closed**
```
Patient : Hi
Bot     : Welcome back, Rahul! 👋  [Book appointment] [Past visits] [Talk to staff]
Patient : Book appointment
Bot     : Booking for Rahul Verma. Which doctor? …   ← name not asked again
```

**Reminder with payment**
```
Bot     : Reminder: Dr. Amit tomorrow, 3:00 PM (APT-7K3Q). ₹500 due.
          [Pay now] [Confirm] [Reschedule] [Cancel]
```

## 9. Edge cases

- The slot is taken while the patient is choosing → suggest the 3 nearest free slots.
- The date is in the past, the doctor is on leave, or the clinic is closed → explain and ask again.
- The patient stops replying partway through → the session expires after 24 hours, and any hold that wasn't confirmed is released.
- The bot doesn't understand the same step 3 times → offer to hand over to staff (§6.5).
- A webhook is delivered twice → it is processed once (deduplicated by message ID or payment event ID).
- A payment succeeds after the hold has expired → the payment is flagged for staff to rebook or refund.
- Staff and the patient change the same appointment at the same moment → optimistic locking means the later change is rejected and asked to retry.
- The 24-hour window has closed → only templates can be sent.
- The doctor is removed or goes on leave and has future appointments → staff get a bulk-reschedule task.

## 10. Non-functional requirements

| Area | Requirement |
|---|---|
| **Architecture** | A layered, SOLID **modular monolith**: one shared platform core plus pluggable modules. Domain logic does not depend on WhatsApp, the web framework, the payment provider or the database. Bot, dashboard and scheduler all call the same application services. |
| **Extensibility** | A new module plugs into extension points: its flows, its router rules, menu items, dashboard routes and event handlers. The core does not change (G6). |
| **Maintainability** | Every feature follows the same layer pattern, so a developer can change any feature by hand by following one example. The code is typed (mypy strict, TS strict) and linted, with tests for each layer. |
| **Tech stack** | Backend: **Python 3.12+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2**. **PostgreSQL**. Hosting on **Vercel** (see §12a): cron jobs plus a jobs table for scheduled work, and Vercel Queues for async work. Frontend: **React + TypeScript (Vite)**. Final choices go in the architecture document. |
| **Security** | Hashed passwords, short-lived JWTs, permission-based access, tenant isolation (in the application and through row-level security), verified WhatsApp and payment webhook signatures, secrets in environment variables or a vault, HTTPS only. |
| **Privacy** | Collect as little data as possible. Encrypt at rest. Keep an audit log of access to personal data. Record consent and honour opt-out. Comply with the data protection law where the tenant operates (for example India's DPDP Act 2023). Delete data automatically under the retention rules in §7.10. |
| **Reliability** | Idempotent webhooks and jobs. Double-booking is prevented by the database. Outgoing messages and payment calls are retried with back-off. |
| **Performance** | Bot reply in ≤ 3 s at p95 (excluding WhatsApp delivery time). Dashboard lists in ≤ 1 s at p95 for 10k appointments per tenant. |
| **Time zones** | Store times in UTC. Display them in the location's time zone. |
| **Observability** | Structured logs with tenant ID and correlation ID, and no personal data in logs. Metrics for messages, flows and payments. |
| **Testability** | WhatsApp, payment, clock and ID generation can all be swapped for fakes, so every flow in §7.1 can be tested end to end without a network. |

## 11. Conceptual data model

```
── Platform core ─────────────────────────────────────────────
Tenant 1──* Location
Tenant 1──* WhatsAppNumber            (phone_number_id → tenant routing)
Tenant 1──* TenantModule              (enabled modules + settings JSON)
Tenant 1──* User *──* Role (per tenant) ── Permission
Tenant 1──* Contact                   (unique tenant_id + phone_e164; consent, opt-out)
Contact 1──0..1 ConversationSession   (module, step, collected data, expires_at)
Contact 1──* Message                  (inbound/outbound, wa_message_id unique, status)
Contact 1──0..1 Handover              (assigned staff, active flag)
Tenant 1──* TemplateMapping           (platform event → approved WA template)
Tenant 1──* PaymentAccount
PaymentRequest *──1 Contact            (amount, status, gateway, gateway ref, subject_type/subject_id)
PaymentRequest 1──* PaymentEvent
ScheduledJob                           (type, run_at, payload, idempotency_key)
AuditLog

── Appointment module ────────────────────────────────────────
Contact 1──* Patient                   (family members share one number)
Location 1──* Doctor 1──* WorkingHours / BlockedTime
Tenant 1──* BookingFieldDefinition
Patient 1──* Case 1──* Appointment *──1 Doctor   (Case: OPEN / CLOSED / PURGED, closed_at, last_activity_at, legal_hold)
Appointment 1──* AppointmentEvent      (append-only history)
Appointment 1──* BookingFieldValue
Appointment 1──0..* ChangeRequest      (pending reschedule with held slot)
Appointment 0..1──* PaymentRequest     (via subject_type = 'appointment')
```

Key constraints:

- Double-booking is prevented by a `slot_reservations` table with a Postgres exclusion constraint on overlapping time ranges per doctor. It covers active appointments and held reschedule slots (see ARCHITECTURE §8.3).
- `Message.wa_message_id` and `PaymentEvent.provider_event_id` are unique, so webhooks are processed once.
- The application database role can only INSERT into `AppointmentEvent`, `PaymentEvent` and `AuditLog`. It cannot UPDATE or DELETE them. Only a separate **purge role**, used by the retention job, can DELETE, and the deletion cascades from the Case.
- `DeletionRecord` (contains no personal data) stores the proof of each purge.
- Row-level security is applied on `tenant_id`.

## 12. Assumptions

- A1: Each tenant uses the official **WhatsApp Business Platform (Meta Cloud API)** with its own number. Embedded Signup onboarding is Phase 2. In Phase 1 the super-admin connects numbers by hand.
- A2: Payments are in INR (India). Each tenant turns on any of: WhatsApp Payments (set up in WhatsApp Business Manager), Razorpay payment links, or Pay at clinic (cash or UPI at the counter).
- A3: Slots are fixed-length and set per doctor.
- A4: The WhatsApp sender number is enough to identify the contact.

## 12a. Hosting and background jobs

| Part | Where it runs |
|---|---|
| Dashboard (React + TypeScript, Vite) | Vercel, as static files on the CDN |
| API, WhatsApp webhook, payment webhook (FastAPI) | Vercel Functions, Python runtime, **Mumbai region (`bom1`)** |
| PostgreSQL | A managed Postgres from the Vercel Marketplace (Neon or Supabase) in **ap-south-1 (Mumbai)**, using the **pooled** connection string |
| Time-based jobs (reminders, request expiry, hold and payment request expiry, retention purge, session clean-up) | Due jobs are stored in the `ScheduledJob` table. A **Vercel Cron** job calls `/internal/jobs/tick` **every minute**. Each tick claims the due jobs with `FOR UPDATE SKIP LOCKED` and runs them. Each job has an idempotency key, so a retried job never sends the same reminder twice. |
| Async work (outgoing WhatsApp messages, retries, heavy webhook processing) | **Vercel Queues** (Python SDK) |
| Real-time dashboard updates | Server-sent events or WebSockets, with automatic reconnect because function run time is limited |

Hosting rules:

- **The Vercel Pro plan is required.** Hobby is for non-commercial use only, and its cron jobs are too infrequent for per-minute ticks.
- **The application code never depends on Vercel directly.** Jobs, queues and real-time updates sit behind interfaces (`JobScheduler`, `TaskQueue`, `EventPublisher`). The same code also builds into a Docker image, so it can move to Render, Railway or AWS by swapping implementations, with no changes to business logic.
- Cron and internal job endpoints check a shared secret (`CRON_SECRET`).
- Keeping all data in the Mumbai region supports compliance with the DPDP Act.

## 13. Open questions

| # | Question | Suggested default |
|---|---|---|
| OQ-1 | How should an approval request reach staff outside the dashboard (WhatsApp to staff, email, push)? | Dashboard notification first. Phase 2: WhatsApp message to the on-duty staff member. |
| OQ-2 | ~~Refund policy~~ **Decided:** with Razorpay links, staff refund from the dashboard. With WhatsApp Payments, the clinic refunds outside the system and staff record it with Mark as refunded (PL-6.5). | — |
| OQ-3 | Should patients pay before or after approval by default? | After approval, so patients never pay for a slot that gets declined |
| OQ-4 | ~~Retention and deletion~~ **Decided:** see §7.10. Retention: 60 days after closing, or 12 months if incomplete. Patients can ask for their personal and health-related data to be deleted (AP-10.8 to AP-10.13). Payment records are never deleted (RT-7). **Still open:** how many years payment records must be kept. | Confirm the period with an accountant. Until then, keep them indefinitely. |
| OQ-5 | ~~Hosting and background jobs~~ **Decided: Vercel.** See §12a. | — |
| OQ-6 | Billing tenants for the platform (subscriptions) | Out of scope for v1 |
| OQ-7 | Which language(s) should the bot speak? | English first. The flow text is kept in translation files so Hindi and other languages can be added. |

## 14. Release plan

| Phase | Scope |
|---|---|
| **Phase 0 – Platform foundations** | Repository skeleton, layered modular architecture, CI, migrations, tenancy and row-level security, auth and permissions, WhatsApp webhook and gateway, conversation engine, audit log |
| **Phase 1 – Appointment MVP** | Greeting routing R1–R11, booking, family profiles, staff approval queue, reschedule and cancel, history, dashboard (requests, appointments, detail timeline, settings), staff inbox with handover |
| **Phase 2 – Engagement and payments** | Reminder templates with action buttons, Payments (WhatsApp Payments, Razorpay links, Pay at clinic) in confirmations and reminders, refunds, Mark as paid / refunded, LLM intent and date parsing, WhatsApp alerts to staff, Embedded Signup |
| **Phase 3 – Platform growth** | Second module (for example feedback surveys or broadcast campaigns), more languages, analytics |

## 15. Acceptance criteria (MVP: Phases 0 and 1)

1. **R1:** A new number says "Hi" → consent and details are collected → one Contact, one Patient, an Appointment in `REQUESTED` with a `REQUESTED` event, and the slot is held.
2. **R2:** The same number says "Hello" → the bot shows the active appointment and the main menu, and asks for no details.
3. **R3:** Once all appointments are final, "Hi" → "Welcome back" → booking reuses the stored name. No new Patient is created.
4. **R4:** A number with 2 patients is asked "Who is this for?". Choosing "Someone new" creates a second Patient under the same Contact.
5. **Approval:** Staff approve → `CONFIRMED`, the patient is told. Staff decline → `DECLINED`, the slot is freed. A request nobody answers → `EXPIRED`.
6. **Reschedule:** Fri 15:00 → Sat 17:00 with approval. The original time stays valid until approval. Afterwards the appointment ID and reference are unchanged, the status is `RESCHEDULED`, the history shows the old and new times, and Fri 15:00 is free.
7. A patient with two active appointments is asked which one to reschedule.
8. Two confirmations for the same slot at the same moment → exactly one succeeds.
9. **Handover:** `AGENT` → the conversation appears in the inbox, the bot is paused, staff replies reach WhatsApp, and the bot resumes when it is handed back.
10. **Isolation:** A user in Tenant A gets 404 for any resource in Tenant B, through the API and directly in the database (row-level security).
11. A webhook delivered twice → one message is processed and one booking is made.
12. The dashboard shows the original and current times and the full timeline for the rescheduled appointment.
13. **Retention:** a case closed by staff is purged 60 days after closing. An open case with no activity for 12 months is purged. Reopening a case before then cancels the purge. Afterwards only a deletion record with no personal data remains, and the same number saying "Hi" is treated as a new patient (R1).
14. **Deletion on request:** `DELETE MY DATA` → the patient confirms → staff approve → the profile, cases, appointments and history are deleted, and the patient gets a WhatsApp confirmation. The payment records stay as ledger entries with no health-related details.
