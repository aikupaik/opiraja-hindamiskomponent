"""Strict JWT issuance and validation for the three credential profiles."""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import jwt

from app.config import Settings

from .auth import (
    ADMIN_SCOPES,
    TESTS_CREATE,
    TESTS_LAUNCH,
    TESTS_PLAY,
    TESTS_READ,
    AuthContext,
)

_ALGORITHM = "HS256"
_LEEWAY_SECONDS = 30
_COMMON_CLAIMS = frozenset({"iss", "aud", "sub", "scope", "iat", "exp"})
_OR_SCOPES = frozenset({TESTS_CREATE, TESTS_READ, TESTS_LAUNCH})


class InvalidBearerToken(RuntimeError):
    """Bearer credentials did not match any valid JWT profile."""


class TokenService:
    def __init__(
        self,
        settings: Settings,
        *,
        now_factory: Callable[[], datetime] | None = None,
        uuid_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._settings = settings
        self._now_factory = now_factory or (lambda: datetime.now(UTC))
        self._uuid_factory = uuid_factory

    def decode(self, token: str) -> AuthContext:
        validators = (self._decode_or, self._decode_player, self._decode_admin)
        for validator in validators:
            try:
                return validator(token)
            except (jwt.PyJWTError, InvalidBearerToken, ValueError, TypeError):
                continue
        raise InvalidBearerToken("valid bearer credentials are required")

    def issue_player(self, test_id: UUID) -> str:
        now = self._now_timestamp()
        canonical_test_id = str(test_id)
        return jwt.encode(
            {
                "iss": "assessment-api",
                "aud": "assessment-player",
                "sub": f"player:{canonical_test_id}",
                "scope": TESTS_PLAY,
                "iat": now,
                "exp": now + self._settings.player_jwt_lifetime_seconds,
                "jti": str(self._uuid_factory()),
                "test_id": canonical_test_id,
            },
            self._settings.api_jwt_secret.get_secret_value(),
            algorithm=_ALGORITHM,
        )

    def issue_admin(self) -> str:
        now = self._now_timestamp()
        return jwt.encode(
            {
                "iss": "assessment-api",
                "aud": "assessment-admin",
                "sub": "development-admin",
                "scope": " ".join(sorted(ADMIN_SCOPES)),
                "iat": now,
                "exp": now + self._settings.admin_jwt_lifetime_seconds,
                "jti": str(self._uuid_factory()),
            },
            self._settings.api_jwt_secret.get_secret_value(),
            algorithm=_ALGORITHM,
        )

    def player_url(self, test_id: UUID, token: str) -> str:
        return f"{self._settings.player_app_url}/test/{test_id}#token={token}"

    def _decode_or(self, token: str) -> AuthContext:
        payload = self._decode_payload(
            token,
            secret=self._settings.or_jwt_secret.get_secret_value(),
            issuer=self._settings.or_jwt_issuer,
            audience="assessment-api",
            claims=_COMMON_CLAIMS,
        )
        subject, scopes, issued_at, expires_at = self._common_values(payload)
        if not scopes or not scopes <= _OR_SCOPES:
            raise InvalidBearerToken("invalid OR scope profile")
        if expires_at - issued_at > self._settings.or_jwt_max_lifetime_seconds:
            raise InvalidBearerToken("OR token lifetime is too long")
        return AuthContext("or", subject, scopes)

    def _decode_player(self, token: str) -> AuthContext:
        claims = _COMMON_CLAIMS | {"jti", "test_id"}
        payload = self._decode_payload(
            token,
            secret=self._settings.api_jwt_secret.get_secret_value(),
            issuer="assessment-api",
            audience="assessment-player",
            claims=claims,
        )
        subject, scopes, _, _ = self._common_values(payload)
        if scopes != frozenset({TESTS_PLAY}):
            raise InvalidBearerToken("invalid player scope profile")
        test_id = self._uuid_claim(payload, "test_id")
        self._uuid_claim(payload, "jti")
        if subject != f"player:{test_id}":
            raise InvalidBearerToken("player subject is not test-bound")
        return AuthContext("player", subject, scopes, test_id)

    def _decode_admin(self, token: str) -> AuthContext:
        payload = self._decode_payload(
            token,
            secret=self._settings.api_jwt_secret.get_secret_value(),
            issuer="assessment-api",
            audience="assessment-admin",
            claims=_COMMON_CLAIMS | {"jti"},
        )
        subject, scopes, _, _ = self._common_values(payload)
        self._uuid_claim(payload, "jti")
        if subject != "development-admin" or scopes != ADMIN_SCOPES:
            raise InvalidBearerToken("invalid admin profile")
        return AuthContext("admin", subject, scopes)

    def _decode_payload(
        self,
        token: str,
        *,
        secret: str,
        issuer: str,
        audience: str,
        claims: frozenset[str],
    ) -> Mapping[str, object]:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            issuer=issuer,
            audience=audience,
            leeway=_LEEWAY_SECONDS,
            options={"require": sorted(claims)},
        )
        if frozenset(payload) != claims:
            raise InvalidBearerToken("JWT contains an unexpected claim set")
        return cast(Mapping[str, object], payload)

    def _common_values(
        self, payload: Mapping[str, object]
    ) -> tuple[str, frozenset[str], int, int]:
        for claim in ("iss", "aud", "sub", "scope"):
            if not isinstance(payload[claim], str):
                raise InvalidBearerToken(f"{claim} must be a string")
        subject = cast(str, payload["sub"])
        if not subject.strip():
            raise InvalidBearerToken("subject must not be blank")
        issued_at = self._integer_claim(payload, "iat")
        expires_at = self._integer_claim(payload, "exp")
        now = self._now_timestamp()
        if expires_at <= issued_at or issued_at > now + _LEEWAY_SECONDS:
            raise InvalidBearerToken("invalid JWT time range")
        scope = cast(str, payload["scope"])
        scopes = scope.split(" ") if scope else []
        if not scopes or " ".join(scopes) != scope or len(set(scopes)) != len(scopes):
            raise InvalidBearerToken("scope is not canonical")
        return subject, frozenset(scopes), issued_at, expires_at

    @staticmethod
    def _integer_claim(payload: Mapping[str, object], name: str) -> int:
        value = payload[name]
        if type(value) is not int:
            raise InvalidBearerToken(f"{name} must be an integer")
        return value

    @staticmethod
    def _uuid_claim(payload: Mapping[str, object], name: str) -> UUID:
        value = payload[name]
        if not isinstance(value, str):
            raise InvalidBearerToken(f"{name} must be a UUID string")
        parsed = UUID(value)
        if str(parsed) != value:
            raise InvalidBearerToken(f"{name} must be a canonical UUID")
        return parsed

    def _now_timestamp(self) -> int:
        return int(self._now_factory().timestamp())
