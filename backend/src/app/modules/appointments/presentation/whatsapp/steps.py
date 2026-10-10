"""WhatsApp steps of the appointments module (PRD §7.1-§7.4, §8). Each step asks ONE question,
skips itself when the answer is already known (DR-5), and calls the SAME use cases as the
dashboard (actor = the contact, channel = WhatsApp).

Session data keys: patient_id, patient_name, new_patient, location_id, doctor_id, day, start,
reason, fields, appointment_id, delete_patients.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from app.modules.appointments.application.commands.booking import RequestAppointmentCommand
from app.modules.appointments.application.commands.changes import CancelCommand, RescheduleCommand
from app.modules.appointments.application.commands.deletion import RequestDeletionCommand
from app.modules.appointments.application.commands.patients import RegisterPatientCommand
from app.modules.appointments.application.dto import AppointmentDTO, DoctorDTO
from app.modules.appointments.application.ports import ClinicDirectory
from app.modules.appointments.application.queries.reads import SlotsQuery
from app.modules.appointments.application.use_cases import AppointmentsUseCases
from app.modules.appointments.domain.errors import (
    ChangeCutoffPassedError,
    InvalidBookingFieldsError,
    InvalidPatientError,
    ReasonRequiredError,
    SlotUnavailableError,
)
from app.modules.appointments.domain.policy import BookingPolicy, FieldType
from app.modules.appointments.presentation.whatsapp.formatting import clock, day_label, local, when
from app.modules.appointments.presentation.whatsapp.parsing import parse_day, parse_time
from app.shared.application.conversation import (
    BaseStep,
    Finish,
    FlowContext,
    InboundReply,
    Next,
    Retry,
    StartFlow,
    StepResult,
)
from app.shared.kernel.actor import Actor, Channel
from app.shared.kernel.ids import TenantId
from app.shared.kernel.messages import Buttons, Choice, ListMenu, menu

BOOK, MENU, RESCHEDULE, CANCEL, DELETE = (
    "appointments.book",
    "appointments.menu",
    "appointments.reschedule",
    "appointments.cancel",
    "appointments.delete_data",
)
#: Start the "delete my data" flow from anywhere (PRD AP-10.8).
DELETE_WORDS = frozenset({"delete my data", "delete data", "erase my data", "delete my details"})
DAYS_TO_OFFER = 10  # a WhatsApp list holds at most 10 rows


@dataclass(frozen=True)
class Bot:
    """What every step needs: this tenant's use cases and clinic facts."""

    use_cases: Callable[[TenantId], AppointmentsUseCases]
    clinic: ClinicDirectory

    def uc(self, ctx: FlowContext) -> AppointmentsUseCases:
        return self.use_cases(ctx.tenant_id)

    async def policy(self, ctx: FlowContext) -> BookingPolicy:
        return BookingPolicy.from_settings(await self.clinic.settings(ctx.tenant_id))

    async def doctor(self, ctx: FlowContext, doctor_id: str) -> DoctorDTO | None:
        doctors = await self.uc(ctx).list_doctors(active_only=True)
        return next((d for d in doctors if str(d.id) == doctor_id), None)

    async def timezone(self, ctx: FlowContext, location_id: UUID) -> str:
        return await self.clinic.timezone(ctx.tenant_id, location_id)


def _actor(ctx: FlowContext) -> Actor:
    return Actor.contact(ctx.contact.id)


def _pick(reply: InboundReply, prefix: str) -> str | None:
    """The id behind a tapped choice "prefix:<id>", or None."""
    if reply.choice_id and reply.choice_id.startswith(prefix + ":"):
        return reply.choice_id.split(":", 1)[1]
    return None


def _spread(items: list[datetime], limit: int) -> list[datetime]:
    """At most `limit` items spread evenly over the day (morning to evening), so a list of
    nine times does not show only 6:00-8:00 AM. Any other free time can still be typed."""
    if len(items) <= limit:
        return items
    step = (len(items) - 1) / (limit - 1)
    return [items[round(i * step)] for i in range(limit)]


def _match_title(reply: InboundReply, options: dict[str, str]) -> str | None:
    """Typed text instead of a tap: a number ("2") or (part of) a title ("amit")."""
    text = reply.normalized
    keys = list(options)
    if text.isdigit() and 1 <= int(text) <= len(keys):
        return keys[int(text) - 1]
    hits = [k for k, title in options.items() if text and text in title.lower()]
    return hits[0] if len(hits) == 1 else None


# =================================================================== booking (§7.2)
class ChoosePatient(BaseStep):
    """R4: who is this for? Skipped for a brand-new contact (we will ask the name)."""

    key = "patient"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def should_skip(self, ctx: FlowContext) -> bool:
        if "patient_id" in ctx.data or ctx.data.get("new_patient"):
            return True
        if not await self.bot.uc(ctx).patients_of_contact(ctx.contact.id):
            ctx.data["new_patient"] = True
            return True
        return False

    async def _options(self, ctx: FlowContext) -> dict[str, str]:
        patients = await self.bot.uc(ctx).patients_of_contact(ctx.contact.id)
        return {str(p.id): p.full_name for p in patients}

    async def prompt(self, ctx: FlowContext) -> None:
        options = await self._options(ctx)
        choices = [Choice(f"patient:{pid}", name[:24]) for pid, name in options.items()]
        choices.append(Choice("patient:new", ctx.t("appointments.book.someone_new")))
        ctx.say(
            menu(ctx.t("appointments.book.who"), choices[:10], button=ctx.t("appointments.choose"))
        )

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        options = await self._options(ctx)
        picked = _pick(reply, "patient") or _match_title(reply, options)
        if picked == "new" or reply.normalized in {"someone new", "someone else", "new"}:
            ctx.data["new_patient"] = True
            return Next()
        if picked in options:
            ctx.data.update(patient_id=picked, patient_name=options[picked])
            return Next()
        return Retry("appointments.book.pick_patient")


class AskPatientName(BaseStep):
    key = "name"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def should_skip(self, ctx: FlowContext) -> bool:
        return "patient_id" in ctx.data

    async def prompt(self, ctx: FlowContext) -> None:
        ctx.say(ctx.t("appointments.book.ask_name"))

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        try:
            patient = await self.bot.uc(ctx).register_patient(
                RegisterPatientCommand(ctx.tenant_id, ctx.contact.id, reply.text, _actor(ctx))
            )
        except InvalidPatientError:
            return Retry("appointments.book.bad_name")
        ctx.data.update(patient_id=str(patient.id), patient_name=patient.full_name)
        return Next()


class AskLocation(BaseStep):
    """Only for clinics with several branches that have doctors (PRD AP-2.1)."""

    key = "location"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def _options(self, ctx: FlowContext) -> dict[str, str]:
        names = await self.bot.clinic.location_names(ctx.tenant_id)
        doctors = await self.bot.uc(ctx).list_doctors(active_only=True)
        with_doctors = {d.location_id for d in doctors}
        return {str(i): n for i, n in names.items() if i in with_doctors}

    async def should_skip(self, ctx: FlowContext) -> bool:
        if "location_id" in ctx.data or "doctor_id" in ctx.data:
            return True
        options = await self._options(ctx)
        if len(options) <= 1:
            if options:
                ctx.data["location_id"] = next(iter(options))
            return True
        return False

    async def prompt(self, ctx: FlowContext) -> None:
        options = await self._options(ctx)
        choices = [Choice(f"location:{i}", n[:24]) for i, n in options.items()]
        ctx.say(
            menu(
                ctx.t("appointments.book.which_location"),
                choices[:10],
                button=ctx.t("appointments.choose"),
            )
        )

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        options = await self._options(ctx)
        picked = _pick(reply, "location") or _match_title(reply, options)
        if picked not in options:
            return Retry("appointments.book.pick_from_list")
        ctx.data["location_id"] = picked
        return Next()


class AskDoctor(BaseStep):
    key = "doctor"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def _doctors(self, ctx: FlowContext) -> list[DoctorDTO]:
        doctors = await self.bot.uc(ctx).list_doctors(active_only=True)
        location = ctx.data.get("location_id")
        return [d for d in doctors if location is None or str(d.location_id) == location]

    async def should_skip(self, ctx: FlowContext) -> bool:
        if "doctor_id" in ctx.data:
            return True
        doctors = await self._doctors(ctx)
        if len(doctors) == 1:
            ctx.data["doctor_id"] = str(doctors[0].id)
            return True
        return False

    async def prompt(self, ctx: FlowContext) -> None:
        doctors = await self._doctors(ctx)
        if not doctors:
            ctx.say(ctx.t("appointments.book.no_doctors"))
            return
        choices = [Choice(f"doctor:{d.id}", d.name[:24], d.specialty[:72] or None) for d in doctors]
        ctx.say(
            ListMenu(
                ctx.t("appointments.book.which_doctor"),
                ctx.t("appointments.doctors"),
                tuple(choices[:10]),
            )
        )

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        doctors = {str(d.id): f"{d.name} {d.specialty}" for d in await self._doctors(ctx)}
        if not doctors:
            ctx.request_handover()
            return Finish()
        picked = _pick(reply, "doctor") or _match_title(reply, doctors)
        if picked not in doctors:
            return Retry("appointments.book.pick_from_list")
        ctx.data["doctor_id"] = picked
        return Next()


class AskDay(BaseStep):
    """Offer only days that still have free slots (PRD §8: "Pick a date")."""

    key = "day"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def _open_days(self, ctx: FlowContext) -> tuple[list[date], str]:
        doctor = await self.bot.doctor(ctx, ctx.data["doctor_id"])
        if doctor is None:
            return [], "UTC"
        timezone = await self.bot.timezone(ctx, doctor.location_id)
        policy = await self.bot.policy(ctx)
        today = local(ctx.now, timezone).date()
        days: list[date] = []
        for offset in range(policy.horizon_days + 1):
            day = today + timedelta(days=offset)
            result = await self.bot.uc(ctx).find_free_slots(
                SlotsQuery(ctx.tenant_id, doctor.id, day)
            )
            if result.slots:
                days.append(day)
            if len(days) == DAYS_TO_OFFER:
                break
        return days, timezone

    async def should_skip(self, ctx: FlowContext) -> bool:
        return "day" in ctx.data

    async def prompt(self, ctx: FlowContext) -> None:
        days, _ = await self._open_days(ctx)
        if not days:
            ctx.say(ctx.t("appointments.book.no_availability"))
            return
        choices = tuple(Choice(f"day:{d.isoformat()}", day_label(d)) for d in days)
        ctx.say(
            ListMenu(ctx.t("appointments.book.which_day"), ctx.t("appointments.dates"), choices)
        )

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        days, timezone = await self._open_days(ctx)
        if not days:
            ctx.request_handover()
            return Finish()
        picked = _pick(reply, "day")
        day = (
            date.fromisoformat(picked)
            if picked
            else parse_day(reply.text, local(ctx.now, timezone).date())
        )
        if day is None:
            return Retry("appointments.book.day_not_understood")
        if day not in days:
            return Retry("appointments.book.day_unavailable", {"day": day_label(day)})
        ctx.data["day"] = day.isoformat()
        return Next()


class AskSlot(BaseStep):
    key = "slot"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def _slots(self, ctx: FlowContext) -> tuple[list[datetime], str]:
        result = await self.bot.uc(ctx).find_free_slots(
            SlotsQuery(
                ctx.tenant_id, UUID(ctx.data["doctor_id"]), date.fromisoformat(ctx.data["day"])
            )
        )
        return [s.start for s in result.slots], result.timezone

    async def should_skip(self, ctx: FlowContext) -> bool:
        return "start" in ctx.data

    async def prompt(self, ctx: FlowContext) -> None:
        starts, timezone = await self._slots(ctx)
        day = day_label(date.fromisoformat(ctx.data["day"]))
        if not starts:
            ctx.say(ctx.t("appointments.book.day_full", day=day))
            return
        shown = _spread(starts, 9)
        choices = [Choice(f"slot:{s.isoformat()}", clock(s, timezone)) for s in shown]
        choices.append(Choice("slot:other_day", ctx.t("appointments.book.other_day")))
        body = ctx.t("appointments.book.which_time", day=day)
        if len(starts) > len(shown):
            body += "\n" + ctx.t("appointments.book.type_a_time")
        ctx.say(ListMenu(body, ctx.t("appointments.times"), tuple(choices)))

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        picked = _pick(reply, "slot")
        if picked == "other_day" or reply.normalized in {"other day", "another day"}:
            ctx.data.pop("day", None)
            return Next("day")
        starts, timezone = await self._slots(ctx)
        if not starts:
            ctx.data.pop("day", None)
            return Next("day")
        if picked:
            chosen = next((s for s in starts if s.isoformat() == picked), None)
        else:
            wanted = parse_time(reply.text)
            chosen = next(
                (s for s in starts if wanted and local(s, timezone).time() == wanted), None
            )
        if chosen is None:
            return Retry("appointments.book.time_unavailable")
        ctx.data["start"] = chosen.isoformat()
        return Next()


class AskReason(BaseStep):
    key = "reason"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def should_skip(self, ctx: FlowContext) -> bool:
        return "reason" in ctx.data or not (await self.bot.policy(ctx)).reason_required

    async def prompt(self, ctx: FlowContext) -> None:
        ctx.say(ctx.t("appointments.book.ask_reason"))

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        try:
            ctx.data["reason"] = (await self.bot.policy(ctx)).clean_reason(reply.text)
        except ReasonRequiredError:
            return Retry("appointments.book.ask_reason_again")
        return Next()


class AskBookingFields(BaseStep):
    """The clinic's own questions (PRD FR-1.3), one at a time. Re-enters itself until done."""

    key = "fields"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def _next_field(self, ctx: FlowContext) -> Any:
        answered = ctx.data.setdefault("fields", {})
        skipped = ctx.data.setdefault("skipped_fields", [])
        policy = await self.bot.policy(ctx)
        return next(
            (f for f in policy.booking_fields if f.key not in answered and f.key not in skipped),
            None,
        )

    async def should_skip(self, ctx: FlowContext) -> bool:
        return await self._next_field(ctx) is None

    async def prompt(self, ctx: FlowContext) -> None:
        field = await self._next_field(ctx)
        label = field.label + ("" if field.required else ctx.t("appointments.book.optional_hint"))
        if field.type is FieldType.CHOICE:
            choices = [Choice(f"field:{o}", o[:24]) for o in field.options]
            ctx.say(menu(label, choices, button=ctx.t("appointments.choose")))
        else:
            ctx.say(label)

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        field = await self._next_field(ctx)
        value = _pick(reply, "field") or reply.text
        if not field.required and reply.normalized in {"skip", "-", "no"}:
            ctx.data["skipped_fields"].append(field.key)
        else:
            try:
                ctx.data["fields"][field.key] = field.clean(value)
            except InvalidBookingFieldsError as exc:
                ctx.say(exc.message)
                return Retry("appointments.book.try_again")
        return Next(self.key) if await self._next_field(ctx) else Next()


class ConfirmBooking(BaseStep):
    key = "confirm"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def prompt(self, ctx: FlowContext) -> None:
        doctor = await self.bot.doctor(ctx, ctx.data["doctor_id"])
        assert doctor is not None
        timezone = await self.bot.timezone(ctx, doctor.location_id)
        summary = ctx.t(
            "appointments.book.summary",
            doctor=doctor.name,
            when=when(datetime.fromisoformat(ctx.data["start"]), timezone),
            patient=ctx.data["patient_name"],
            reason=ctx.data.get("reason") or "-",
        )
        ctx.say(
            Buttons(
                summary,
                (
                    Choice("confirm:yes", ctx.t("appointments.confirm_button")),
                    Choice("confirm:change", ctx.t("appointments.change_button")),
                ),
            )
        )

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        answer = _pick(reply, "confirm") or {
            "yes": "yes",
            "confirm": "yes",
            "ok": "yes",
            "change": "change",
        }.get(reply.normalized)
        if answer == "change":
            for key in ("doctor_id", "location_id", "day", "start"):
                ctx.data.pop(key, None)
            return Next("location")
        if answer != "yes":
            return Retry("appointments.book.confirm_or_change")
        try:
            booked = await self.bot.uc(ctx).request(
                RequestAppointmentCommand(
                    ctx.tenant_id,
                    UUID(ctx.data["patient_id"]),
                    UUID(ctx.data["doctor_id"]),
                    datetime.fromisoformat(ctx.data["start"]),
                    _actor(ctx),
                    Channel.WHATSAPP,
                    ctx.data.get("reason"),
                    ctx.data.get("fields", {}),
                )
            )
        except SlotUnavailableError:
            ctx.say(ctx.t("appointments.book.just_taken"))
            ctx.data.pop("start", None)
            return Next("slot")
        timezone = await self.bot.timezone(ctx, booked.location_id)
        key = (
            "appointments.book.requested"
            if booked.status == "requested"
            else "appointments.book.confirmed"
        )
        ctx.say(
            ctx.t(
                key,
                ref=booked.reference,
                when=when(booked.slot.start, timezone),
                doctor=booked.doctor_name,
            )
        )
        return Finish()


# =================================================================== returning contacts (§7.1)
STATUS_KEYS = {
    "requested": "appointments.status.requested",
    "confirmed": "appointments.status.confirmed",
    "rescheduled": "appointments.status.confirmed",
}


async def _describe(bot: Bot, ctx: FlowContext, a: AppointmentDTO) -> str:
    timezone = await bot.timezone(ctx, a.location_id)
    status = ctx.t(STATUS_KEYS.get(a.status, "appointments.status.confirmed"))
    if a.pending_slot is not None:
        status = ctx.t(
            "appointments.status.change_requested", when=when(a.pending_slot.start, timezone)
        )
    return ctx.t(
        "appointments.menu.line",
        patient=a.patient_name,
        doctor=a.doctor_name,
        when=when(a.slot.start, timezone),
        ref=a.reference,
        status=status,
    )


async def _changeable(bot: Bot, ctx: FlowContext) -> list[AppointmentDTO]:
    """Active appointments the PATIENT may still change (outside the cut-off - R10)."""
    policy = await bot.policy(ctx)
    upcoming = await bot.uc(ctx).upcoming_for_contact(ctx.contact.id)
    return [
        a
        for a in upcoming
        if a.status == "requested" or a.slot.start - policy.change_cutoff > ctx.now
    ]


class MainMenu(BaseStep):
    """R2 (has upcoming), R3 (welcome back), R5 (waiting for the clinic), R9 (opted out),
    R10 (too close to change). Options appear only when they make sense (§7.1)."""

    key = "menu"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def _options(self, ctx: FlowContext) -> list[Choice]:
        upcoming = await self.bot.uc(ctx).upcoming_for_contact(ctx.contact.id)
        changeable = await _changeable(self.bot, ctx)
        options = []
        if changeable:
            options.append(Choice("menu:reschedule", ctx.t("appointments.menu.reschedule")))
            options.append(Choice("menu:cancel", ctx.t("appointments.menu.cancel")))
        label = "appointments.menu.book_another" if upcoming else "appointments.menu.book"
        options.append(Choice("menu:book", ctx.t(label)))
        options.append(Choice("menu:staff", ctx.t("appointments.menu.staff")))
        options.append(Choice("menu:delete", ctx.t("appointments.menu.delete_data")))
        return options

    async def prompt(self, ctx: FlowContext) -> None:
        upcoming = await self.bot.uc(ctx).upcoming_for_contact(ctx.contact.id)
        patients = await self.bot.uc(ctx).patients_of_contact(ctx.contact.id)
        name = patients[0].full_name.split()[0] if patients else (ctx.contact.profile_name or "")
        lines = [ctx.t("appointments.menu.hello", name=name).replace(" !", "!")]
        if upcoming:
            lines.append(ctx.t("appointments.menu.your_appointments"))
            lines += [await _describe(self.bot, ctx, a) for a in upcoming[:5]]
            if len(await _changeable(self.bot, ctx)) < len(upcoming):
                lines.append(ctx.t("appointments.menu.too_close"))
        else:
            lines.append(ctx.t("appointments.menu.no_upcoming"))
        if ctx.contact.is_opted_out:
            lines.append(ctx.t("appointments.menu.opted_out"))
        ctx.say(
            menu("\n".join(lines), await self._options(ctx), button=ctx.t("appointments.options"))
        )

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        options = {c.id.split(":", 1)[1]: c.title for c in await self._options(ctx)}
        picked = _pick(reply, "menu") or _match_title(reply, options)
        words = {
            "book": "book",
            "reschedule": "reschedule",
            "change": "reschedule",
            "cancel": "cancel",
        }
        picked = picked or words.get(reply.normalized)
        if picked not in options:
            return Retry("appointments.book.pick_from_list")
        if picked == "staff":
            ctx.say(ctx.t("conversations.agent_requested"))
            ctx.request_handover()
            return Finish()
        flows = {"book": BOOK, "reschedule": RESCHEDULE, "cancel": CANCEL, "delete": DELETE}
        return StartFlow(flows[picked])


class PickAppointment(BaseStep):
    """AP-4.1: one changeable appointment -> chosen automatically; several -> ask which."""

    key = "pick"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def should_skip(self, ctx: FlowContext) -> bool:
        if "appointment_id" in ctx.data:
            return True
        candidates = await _changeable(self.bot, ctx)
        if len(candidates) == 1:
            self._choose(ctx, candidates[0])
            return True
        return False

    def _choose(self, ctx: FlowContext, a: AppointmentDTO) -> None:
        ctx.data.update(appointment_id=str(a.id), doctor_id=str(a.slot.doctor_id))

    async def prompt(self, ctx: FlowContext) -> None:
        candidates = await _changeable(self.bot, ctx)
        if not candidates:
            ctx.say(ctx.t("appointments.change.none"))
            return
        choices = []
        for a in candidates[:10]:
            timezone = await self.bot.timezone(ctx, a.location_id)
            choices.append(
                Choice(
                    f"appt:{a.id}",
                    a.reference,
                    f"{a.doctor_name}, {when(a.slot.start, timezone)}"[:72],
                )
            )
        ctx.say(
            ListMenu(
                ctx.t("appointments.change.which"),
                ctx.t("appointments.appointments"),
                tuple(choices),
            )
        )

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        candidates = {str(a.id): a for a in await _changeable(self.bot, ctx)}
        if not candidates:
            return StartFlow(MENU)
        picked = _pick(reply, "appt") or _match_title(
            reply, {k: a.reference for k, a in candidates.items()}
        )
        if picked not in candidates:
            return Retry("appointments.book.pick_from_list")
        self._choose(ctx, candidates[picked])
        return Next()


class ConfirmReschedule(BaseStep):
    key = "confirm"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def prompt(self, ctx: FlowContext) -> None:
        doctor = await self.bot.doctor(ctx, ctx.data["doctor_id"])
        timezone = await self.bot.timezone(ctx, doctor.location_id) if doctor else "UTC"
        ctx.say(
            Buttons(
                ctx.t(
                    "appointments.change.confirm_move",
                    when=when(datetime.fromisoformat(ctx.data["start"]), timezone),
                ),
                (
                    Choice("confirm:yes", ctx.t("appointments.confirm_button")),
                    Choice("confirm:change", ctx.t("appointments.change_button")),
                ),
            )
        )

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        answer = _pick(reply, "confirm") or {"yes": "yes", "ok": "yes", "change": "change"}.get(
            reply.normalized
        )
        if answer == "change":
            ctx.data.pop("day", None)
            ctx.data.pop("start", None)
            return Next("day")
        if answer != "yes":
            return Retry("appointments.book.confirm_or_change")
        try:
            moved = await self.bot.uc(ctx).reschedule(
                RescheduleCommand(
                    ctx.tenant_id,
                    UUID(ctx.data["appointment_id"]),
                    datetime.fromisoformat(ctx.data["start"]),
                    _actor(ctx),
                    Channel.WHATSAPP,
                )
            )
        except SlotUnavailableError:
            ctx.say(ctx.t("appointments.book.just_taken"))
            ctx.data.pop("start", None)
            return Next("slot")
        except ChangeCutoffPassedError:
            ctx.say(ctx.t("appointments.change.too_late"))
            return Finish()
        timezone = await self.bot.timezone(ctx, moved.location_id)
        if moved.pending_slot is not None:
            ctx.say(
                ctx.t(
                    "appointments.change.requested",
                    ref=moved.reference,
                    when=when(moved.pending_slot.start, timezone),
                )
            )
        else:
            ctx.say(
                ctx.t(
                    "appointments.change.done",
                    ref=moved.reference,
                    when=when(moved.slot.start, timezone),
                )
            )
        return Finish()


class ConfirmCancel(BaseStep):
    key = "confirm_cancel"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def prompt(self, ctx: FlowContext) -> None:
        upcoming = await self.bot.uc(ctx).upcoming_for_contact(ctx.contact.id)
        appointment = next(a for a in upcoming if str(a.id) == ctx.data["appointment_id"])
        ctx.say(
            Buttons(
                ctx.t(
                    "appointments.cancel.confirm", line=await _describe(self.bot, ctx, appointment)
                ),
                (
                    Choice("cancel:yes", ctx.t("appointments.cancel.yes")),
                    Choice("cancel:no", ctx.t("appointments.cancel.no")),
                ),
            )
        )

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        answer = _pick(reply, "cancel") or {"yes": "yes", "no": "no"}.get(reply.normalized)
        if answer == "no":
            ctx.say(ctx.t("appointments.cancel.kept"))
            return Finish()
        if answer != "yes":
            return Retry("appointments.book.pick_from_list")
        try:
            cancelled = await self.bot.uc(ctx).cancel(
                CancelCommand(
                    ctx.tenant_id,
                    UUID(ctx.data["appointment_id"]),
                    _actor(ctx),
                    Channel.WHATSAPP,
                    "Cancelled by patient",
                )
            )
        except ChangeCutoffPassedError:
            ctx.say(ctx.t("appointments.change.too_late"))
            return Finish()
        ctx.say(ctx.t("appointments.cancel.done", ref=cancelled.reference))
        return Finish()


# =================================================================== delete my data (§7.10)
class ChooseWhoToDelete(BaseStep):
    """AP-10.12: several patients on this number -> whose data (or everyone's)?"""

    key = "delete_who"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def should_skip(self, ctx: FlowContext) -> bool:
        if "delete_patients" in ctx.data:
            return True
        if await self.bot.uc(ctx).pending_deletion_of(ctx.contact.id):
            ctx.say(ctx.t("appointments.delete.already"))
            ctx.data["delete_patients"] = []
            return True
        patients = await self.bot.uc(ctx).patients_of_contact(ctx.contact.id)
        if len(patients) > 1:
            return False
        if not patients:
            ctx.say(ctx.t("appointments.delete.nothing"))
        ctx.data["delete_patients"] = [str(p.id) for p in patients]
        return True

    async def _options(self, ctx: FlowContext) -> dict[str, str]:
        patients = await self.bot.uc(ctx).patients_of_contact(ctx.contact.id)
        return {str(p.id): p.full_name for p in patients}

    async def prompt(self, ctx: FlowContext) -> None:
        choices = [
            Choice(f"del:{pid}", name[:24]) for pid, name in (await self._options(ctx)).items()
        ]
        choices = [*choices[:9], Choice("del:all", ctx.t("appointments.delete.everyone"))]
        ctx.say(
            menu(ctx.t("appointments.delete.who"), choices, button=ctx.t("appointments.choose"))
        )

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        options = await self._options(ctx)
        picked = _pick(reply, "del") or _match_title(reply, options)
        if picked == "all" or reply.normalized in {"everyone", "all"}:
            ctx.data["delete_patients"] = list(options)
        elif picked in options:
            ctx.data["delete_patients"] = [picked]
        else:
            return Retry("appointments.book.pick_from_list")
        return Next()


class ConfirmDeletion(BaseStep):
    """AP-10.9: say what goes and what stays (payments), then ask to confirm."""

    key = "delete_confirm"

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def should_skip(self, ctx: FlowContext) -> bool:
        return not ctx.data.get("delete_patients")

    async def prompt(self, ctx: FlowContext) -> None:
        patients = await self.bot.uc(ctx).patients_of_contact(ctx.contact.id)
        chosen = set(ctx.data["delete_patients"])
        names = ", ".join(p.full_name for p in patients if str(p.id) in chosen)
        ctx.say(
            Buttons(
                ctx.t("appointments.delete.explain", names=names),
                (
                    Choice("delete:yes", ctx.t("appointments.delete.yes")),
                    Choice("delete:no", ctx.t("appointments.delete.no")),
                ),
            )
        )

    async def handle(self, ctx: FlowContext, reply: InboundReply) -> StepResult:
        answer = _pick(reply, "delete") or {"yes": "yes", "no": "no"}.get(reply.normalized)
        if answer == "no":
            ctx.say(ctx.t("appointments.delete.kept"))
            return Finish()
        if answer != "yes":
            return Retry("appointments.book.pick_from_list")
        await self.bot.uc(ctx).request_deletion(
            RequestDeletionCommand(
                ctx.tenant_id,
                ctx.contact.id,
                tuple(UUID(p) for p in ctx.data["delete_patients"]),
            )
        )
        ctx.say(ctx.t("appointments.delete.requested"))
        return Finish()
