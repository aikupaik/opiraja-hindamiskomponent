"""Replaceable authorization seams for OR and player routes."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Identity and grants supplied by the authorization boundary."""

    actor_type: Literal["or", "player"]
    subject: str
    scopes: frozenset[str]
    authorized_test_id: UUID | None = None


class AuthorizationDenied(RuntimeError):
    """The caller is not permitted to use the requested operation."""


async def authorize_or() -> AuthContext:
    """Phase-one permissive OR authorization dependency."""

    return AuthContext(
        actor_type="or",
        subject="phase-one-or",
        scopes=frozenset({"tests:create", "tests:read"}),
    )


async def authorize_player(test_id: UUID) -> AuthContext:
    """Phase-one permissive player dependency bound to the path test ID."""

    return AuthContext(
        actor_type="player",
        subject="phase-one-player",
        scopes=frozenset({"tests:play"}),
        authorized_test_id=test_id,
    )


def require_or(context: AuthContext, scope: str) -> None:
    if context.actor_type != "or" or scope not in context.scopes:
        raise AuthorizationDenied("operation is not authorized")


def require_player(context: AuthContext, test_id: UUID) -> None:
    if (
        context.actor_type != "player"
        or "tests:play" not in context.scopes
        or context.authorized_test_id != test_id
    ):
        raise AuthorizationDenied("operation is not authorized")
