"""Replaceable authorization seams for OR, player, and admin routes."""

from dataclasses import dataclass
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
TESTS_LAUNCH = "tests:launch"
ADMIN_SCOPES = frozenset(
    {
        ADMIN_READ,
        ADMIN_WRITE,
        ADMIN_DIAGNOSTICS,
        ADMIN_SIMULATION,
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


def _validated_context(
    request: Request, credentials: HTTPAuthorizationCredentials | None
) -> AuthContext:
    from .tokens import InvalidBearerToken, TokenService

    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise InvalidBearerToken("valid bearer credentials are required")
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise InvalidBearerToken("authorization configuration is unavailable")
    service = getattr(request.app.state, "token_service", None)
    if not isinstance(service, TokenService):
        service = TokenService(settings)
    return service.decode(credentials.credentials)


def authenticated_admin_from_header(
    request: Request, authorization: str
) -> AuthContext | None:
    """Resolve the admin profile for middleware that cannot use dependencies."""

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token:
        return None
    try:
        context = _validated_context(
            request,
            HTTPAuthorizationCredentials(scheme=scheme, credentials=token),
        )
    except RuntimeError:
        return None
    return context if context.actor_type == "admin" else None


async def authorize_admin(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    return _validated_context(request, credentials)


async def authorize_or(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    return _validated_context(request, credentials)


async def authorize_player(
    test_id: UUID,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    return _validated_context(request, credentials)


def require_or(
    context: AuthContext, scope: str, *, allow_admin_simulation: bool = False
) -> None:
    is_or = context.actor_type == "or" and scope in context.scopes
    is_admin_simulation = (
        allow_admin_simulation
        and context.actor_type == "admin"
        and ADMIN_SIMULATION in context.scopes
    )
    if not (is_or or is_admin_simulation):
        raise AuthorizationDenied("operation is not authorized")


def require_player(
    context: AuthContext, test_id: UUID, *, allow_admin_simulation: bool = False
) -> None:
    is_bound_player = (
        context.actor_type == "player"
        and TESTS_PLAY in context.scopes
        and context.authorized_test_id == test_id
    )
    is_admin_simulation = (
        allow_admin_simulation
        and context.actor_type == "admin"
        and ADMIN_SIMULATION in context.scopes
    )
    if not (is_bound_player or is_admin_simulation):
        raise AuthorizationDenied("operation is not authorized")


def require_admin(context: AuthContext, scope: str) -> None:
    if context.actor_type != "admin" or scope not in context.scopes:
        raise AuthorizationDenied("operation is not authorized")
