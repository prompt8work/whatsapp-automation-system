"""Authentication + permission dependencies for routes (ARCHITECTURE §8.8).

    @router.get("/contacts")
    async def list_contacts(ctx: Annotated[RequestContext, Depends(require("contact.read"))]): ...

- `get_principal`      valid access token (any user, tenant optional) - e.g. /auth/me
- `get_request_context` valid token AND a tenant selected               - tenant-scoped routes
- `require(perm)`       ... AND the user's role grants `perm`            - most routes
- `require_super_admin` platform operator only                          - /platform/*

The token verifier is put on `app.state.access_token_verifier` by the app factory, so this
module does not depend on the identity module.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException, Request, status

from app.shared.application.auth import AccessTokenVerifier, InvalidAccessTokenError, Principal
from app.shared.kernel.actor import Actor
from app.shared.kernel.ids import TenantId


@dataclass(frozen=True)
class RequestContext:
    tenant_id: TenantId
    principal: Principal

    @property
    def actor(self) -> Actor:
        return self.principal.actor


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )


async def get_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Not authenticated")
    verifier = cast(AccessTokenVerifier, request.app.state.access_token_verifier)
    try:
        return verifier.verify(token)
    except InvalidAccessTokenError as exc:
        raise _unauthorized("Invalid or expired token") from exc


PrincipalDep = Annotated[Principal, Depends(get_principal)]


async def get_request_context(principal: PrincipalDep) -> RequestContext:
    if principal.tenant_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Select a tenant first")
    return RequestContext(tenant_id=principal.tenant_id, principal=principal)


def require(permission: str) -> Callable[..., Awaitable[RequestContext]]:
    async def dependency(
        ctx: Annotated[RequestContext, Depends(get_request_context)],
    ) -> RequestContext:
        if not ctx.principal.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")
        return ctx

    return dependency


async def require_super_admin(principal: PrincipalDep) -> Principal:
    if not principal.is_super_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform administrators only")
    return principal
