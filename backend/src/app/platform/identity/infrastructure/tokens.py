"""Short-lived JWT access tokens (HS256).

The token carries only ids and the role; permissions are looked up from the role on every
request (PermissionRegistry), so a role's permission set can change without new tokens.
A changed MEMBERSHIP takes effect on the next refresh (at most ACCESS_TTL later).
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import jwt

from app.platform.identity.application.ports import IssuedAccessToken
from app.shared.application.auth import InvalidAccessTokenError, Principal
from app.shared.application.permissions import PermissionRegistry
from app.shared.kernel.clock import Clock
from app.shared.kernel.ids import TenantId
from app.shared.kernel.roles import Role

_ALGORITHM = "HS256"
_ISSUER = "wa-platform"


class JwtAccessTokens:
    """Implements both AccessTokenIssuer (identity) and AccessTokenVerifier (shared)."""

    def __init__(
        self, secret: str, ttl: timedelta, clock: Clock, permissions: PermissionRegistry
    ) -> None:
        if len(secret) < 32:
            raise ValueError("JWT secret must be at least 32 characters")
        self._secret, self._ttl, self._clock, self._permissions = secret, ttl, clock, permissions

    def issue(self, principal: Principal) -> IssuedAccessToken:
        now = self._clock.now()
        expires_at = now + self._ttl
        claims = {
            "iss": _ISSUER,
            "typ": "access",
            "sub": str(principal.user_id),
            "tid": str(principal.tenant_id) if principal.tenant_id else None,
            "role": principal.role.value if principal.role else None,
            "sa": principal.is_super_admin,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return IssuedAccessToken(jwt.encode(claims, self._secret, _ALGORITHM), expires_at)

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[_ALGORITHM],
                issuer=_ISSUER,
                # Expiry is checked below with OUR clock (testable), not PyJWT's system clock.
                options={"require": ["exp", "sub", "iss"], "verify_exp": False},
            )
            if claims.get("typ") != "access":
                raise InvalidAccessTokenError()
            if claims["exp"] <= self._clock.now().timestamp():
                raise InvalidAccessTokenError()
            role = Role(claims["role"]) if claims.get("role") else None
            return Principal(
                user_id=UUID(claims["sub"]),
                tenant_id=TenantId(UUID(claims["tid"])) if claims.get("tid") else None,
                role=role,
                is_super_admin=bool(claims.get("sa")),
                permissions=self._permissions.for_role(role),
            )
        except (jwt.PyJWTError, ValueError, KeyError) as exc:
            raise InvalidAccessTokenError() from exc
