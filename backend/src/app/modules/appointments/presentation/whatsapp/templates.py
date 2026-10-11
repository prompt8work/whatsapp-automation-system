"""Messages the appointments module may send OUTSIDE the 24 h window (PRD PL-4.2). Each
clinic maps every slot to one of its Meta-approved templates (Settings → WhatsApp templates);
without a mapping, such a message is skipped (and the patient sees it on their next visit
to the chat, e.g. "Pay now" in the menu)."""

from __future__ import annotations

from app.shared.application.messaging import TemplateFallback, TemplateSlot

TEMPLATE_SLOTS = (
    TemplateSlot(
        "appointments.reminder",
        "Appointment reminder (sent 24 h / 2 h before, or as set in Booking rules)",
        params=("patient name", "doctor", "date and time", "reference"),
        buttons=("Confirm", "Reschedule", "Cancel"),
        example="Reminder: {{1}} has an appointment with {{2}} on {{3}} (ref {{4}}).",
    ),
    TemplateSlot(
        "appointments.reminder_pay",
        "Appointment reminder when the consultation fee is still due",
        params=("patient name", "doctor", "date and time", "reference", "amount due"),
        buttons=("Confirm", "Reschedule", "Cancel", "Pay now"),
        example="Reminder: {{1}} has an appointment with {{2}} on {{3}} (ref {{4}}). "
        "{{5}} is due - pay now or at the clinic.",
    ),
    TemplateSlot(
        "appointments.payment_due",
        "Payment request after the clinic confirms an appointment",
        params=("amount", "reference"),
        buttons=("Pay now",),
        example="The consultation fee of {{1}} for appointment {{2}} is due.",
    ),
    TemplateSlot(
        "appointments.update",
        "Any other update from the clinic (confirmed, declined, moved, cancelled, receipts ...)",
        params=("message",),
        example="Update about your appointment: {{1}}",
    ),
)


def update_fallback(text: str) -> TemplateFallback:
    return TemplateFallback("appointments.update", (text,))
