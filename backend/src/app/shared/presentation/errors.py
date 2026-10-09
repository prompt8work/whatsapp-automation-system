"""Map `DomainError.code` -> HTTP status in ONE place (ARCHITECTURE §6.4).

Response body is always `{"code": "...", "message": "..."}` so the frontend can switch on `code`.
Modules add their own codes through `ModuleDefinition.http_error_status`.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.shared.kernel.errors import DomainError

BASE_STATUS: Mapping[str, int] = {
    "not_found": 404,
    "concurrency.conflict": 409,
    "validation.failed": 422,
    "auth.invalid_token": 401,
    "auth.permission_denied": 403,
    "auth.no_tenant": 403,
}


def register_error_handlers(app: FastAPI, extra_status: Mapping[str, int]) -> None:
    status_by_code = {**BASE_STATUS, **extra_status}

    async def handle_domain_error(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, DomainError)
        return JSONResponse(
            status_code=status_by_code.get(exc.code, 400),
            content={"code": exc.code, "message": exc.message},
        )

    app.add_exception_handler(DomainError, handle_domain_error)
