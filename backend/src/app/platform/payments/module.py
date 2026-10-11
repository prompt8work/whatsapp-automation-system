from __future__ import annotations

from app.platform.payments.presentation.http.routers import HTTP_ERROR_STATUS
from app.shared.kernel.roles import Role
from app.shared.module import ModuleDefinition

# Gateways need an HTTP client and the credentials key, so bootstrap builds the payments core
# (container.py) and mounts its routers (main.py); the expiry job is registered there too.
module = ModuleDefinition(
    key="payments",
    http_error_status=HTTP_ERROR_STATUS,
    permissions={
        "payment.read": "See payments and receipts",
        "payment.mark": "Mark payments as paid or refunded, cancel and refund them",
        "payment.settings.manage": "Choose payment methods and enter payment keys",
    },
    role_grants={Role.STAFF: {"payment.read", "payment.mark"}},
    live_topics={
        e: ("payments",)
        for e in (
            "PaymentRequested",
            "PaymentSucceeded",
            "PaymentFailed",
            "PaymentExpired",
            "PaymentRefunded",
        )
    },
)
