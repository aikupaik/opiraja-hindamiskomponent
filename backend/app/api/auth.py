"""Replaceable authorization seams for OR, player, and admin routes."""

from dataclasses import dataclass
import secrets
from typing import Literal
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Annotated

from app.config import Settings

ADMIN_READ = "admin:read"
ADMIN_WRITE = "admin:write"
ADMIN_DIAGNOSTICS = "admin:diagnostics"
ADMIN_SIMULATION = "admin:simulation"
TESTS_CREATE = "tests:create"
TESTS_READ = "tests:read"
TESTS_PLAY = "tests:play"
ADMIN_SCOPES = frozenset(
    {
        ADMIN_READ,
        ADMIN_WRITE,
        ADMIN_DIAGNOSTICS,
        ADMIN_SIMULATION,
        TESTS_CREATE,
        TESTS_READ,
        TESTS_PLAY,
    }
)
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Identity and grants supplied by the authorization boundary."""

    actor_type: Literal["or", "player", "admin"]
    subject: str
    scopes: frozenset[str]
    authorized_test_id: UUID | None = None


class AuthorizationDenied(RuntimeError):
    """The caller is not permitted to use the requested operation."""


class AdminUnauthorized(RuntimeError):
    """Admin credentials are missing, invalid, or disabled."""


def _validated_admin(
    request: Request, credentials: HTTPAuthorizationCredentials | None
) -> AuthContext | None:
    settings = request.app.state.settings
    if not isinstance(settings, Settings) or settings.admin_access_key is None:
        return None
    if credentials is None or credentials.scheme.casefold() != "bearer":
        return None
    expected = settings.admin_access_key.get_secret_value()
    if not secrets.compare_digest(
        credentials.credentials.encode("utf-8"), expected.encode("utf-8")
    ):
        return None
    return AuthContext(
        actor_type="admin",
        subject="development-admin",
        scopes=ADMIN_SCOPES,
    )


async def authorize_admin(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    context = _validated_admin(request, credentials)
    if context is None:
        raise AdminUnauthorized("valid admin credentials are required")
    return context


async def authorize_or(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    """Phase-one permissive OR authorization dependency."""

    admin = _validated_admin(request, credentials)
    if admin is not None:
        return admin
    return AuthContext(
        actor_type="or",
        subject="phase-one-or",
        scopes=frozenset({TESTS_CREATE, TESTS_READ}),
    )


async def authorize_player(
    test_id: UUID,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    """Phase-one permissive player dependency bound to the path test ID."""

    admin = _validated_admin(request, credentials)
    if admin is not None:
        return admin
    return AuthContext(
        actor_type="player",
        subject="phase-one-player",
        scopes=frozenset({TESTS_PLAY}),
        authorized_test_id=test_id,
    )


def require_or(context: AuthContext, scope: str) -> None:
    if context.actor_type not in {"or", "admin"} or scope not in context.scopes:
        raise AuthorizationDenied("operation is not authorized")


def require_player(context: AuthContext, test_id: UUID) -> None:
    if (
        TESTS_PLAY not in context.scopes
        or (context.actor_type == "player" and context.authorized_test_id != test_id)
        or context.actor_type not in {"player", "admin"}
    ):
        raise AuthorizationDenied("operation is not authorized")


def require_admin(context: AuthContext, scope: str) -> None:
    if context.actor_type != "admin" or scope not in context.scopes:
        raise AuthorizationDenied("operation is not authorized")
