from __future__ import annotations

from app.platform.messaging.infrastructure.tables import messages
from app.platform.messaging.presentation.http.routers import HTTP_ERROR_STATUS
from app.shared.infrastructure.forget import CONTACT_FORGOTTEN, forget_rows_in
from app.shared.module import ModuleDefinition

# The credentials router and the retry job handler need the gateway/credential store that
# bootstrap builds, so app/main.py and bootstrap/container.py wire them explicitly.
module = ModuleDefinition(
    key="messaging",
    http_error_status=HTTP_ERROR_STATUS,
    event_handlers={CONTACT_FORGOTTEN: [forget_rows_in(messages)]},  # retention RT-4
)
