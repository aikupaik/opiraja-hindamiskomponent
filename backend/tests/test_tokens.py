"""JWT profile, claim, issuance, and rotation contract coverage."""

import time
import json
from collections.abc import Mapping
from typing import cast
from uuid import UUID

import jwt
import pytest
from pydantic import ValidationError

from app.api.auth import ADMIN_SCOPES, TESTS_CREATE, TESTS_LAUNCH, TESTS_PLAY
from app.api.tokens import InvalidBearerToken, TokenService
from app.config import Settings

OR_SECRET = "or-test-secret-00000000000000000000000000000000"
API_SECRET = "api-test-secret-0000000000000000000000000000000"
TEST_ID = UUID("10000000-0000-4000-8000-000000000001")


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_KEY": "service-secret",
        "R_SERVICE_URL": "http://r-service:8000",
        "ALLOWED_HOSTS": ["testserver"],
        "OR_JWT_SECRET": OR_SECRET,
        "API_JWT_SECRET": API_SECRET,
        "OR_JWT_ISSUER": "test-or",
        "PLAYER_APP_URL": "http://localhost:5173/",
    }
    values.update(overrides)
    return Settings.model_validate(values)


def _or_payload(**overrides: object) -> dict[str, object]:
    now = int(time.time())
    payload: dict[str, object] = {
        "iss": "test-or",
        "aud": "assessment-api",
        "sub": "or-service",
        "scope": f"{TESTS_CREATE} {TESTS_LAUNCH}",
        "iat": now,
        "exp": now + 300,
    }
    payload.update(overrides)
    return payload


def _encode(
    payload: Mapping[str, object], *, secret: str = OR_SECRET, algorithm: str = "HS256"
) -> str:
    try:
        return jwt.encode(dict(payload), secret, algorithm=algorithm)
    except TypeError:
        return jwt.api_jws.encode(
            json.dumps(payload).encode("utf-8"), secret, algorithm=algorithm
        )


def test_or_profile_accepts_only_canonical_subset_and_maximum_lifetime() -> None:
    service = TokenService(_settings())
    context = service.decode(_encode(_or_payload()))
    assert context.actor_type == "or"
    assert context.subject == "or-service"
    assert context.scopes == frozenset({TESTS_CREATE, TESTS_LAUNCH})

    for scope in (
        "",
        f" {TESTS_CREATE}",
        f"{TESTS_CREATE} ",
        f"{TESTS_CREATE}  {TESTS_LAUNCH}",
        f"{TESTS_CREATE} {TESTS_CREATE}",
        "admin:read",
    ):
        with pytest.raises(InvalidBearerToken):
            service.decode(_encode(_or_payload(scope=scope)))
    now = int(time.time())
    with pytest.raises(InvalidBearerToken):
        service.decode(_encode(_or_payload(iat=now, exp=now + 301)))


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("iss", 1),
        ("aud", ["assessment-api"]),
        ("sub", "  "),
        ("scope", [TESTS_CREATE]),
        ("iat", True),
        ("iat", 1.5),
        ("exp", False),
        ("exp", 1.5),
    ],
)
def test_mistyped_common_claims_are_rejected(claim: str, value: object) -> None:
    with pytest.raises(InvalidBearerToken):
        TokenService(_settings()).decode(_encode(_or_payload(**{claim: value})))


def test_missing_extra_bad_time_signature_and_algorithm_are_rejected() -> None:
    service = TokenService(_settings())
    missing = _or_payload()
    del missing["sub"]
    invalid_payloads = (
        missing,
        _or_payload(extra="unexpected"),
        _or_payload(iat=int(time.time()) + 31, exp=int(time.time()) + 60),
        _or_payload(iat=int(time.time()), exp=int(time.time())),
    )
    for payload in invalid_payloads:
        with pytest.raises(InvalidBearerToken):
            service.decode(_encode(payload))
    with pytest.raises(InvalidBearerToken):
        service.decode(_encode(_or_payload(), secret="wrong-secret" * 4))
    with pytest.raises(InvalidBearerToken):
        service.decode(_encode(_or_payload(), secret=OR_SECRET * 2, algorithm="HS384"))


def test_thirty_second_clock_leeway_is_applied_to_future_and_expiry_checks() -> None:
    service = TokenService(_settings())
    now = int(time.time())
    assert service.decode(
        _encode(_or_payload(iat=now + 30, exp=now + 60))
    ).actor_type == "or"
    assert service.decode(
        _encode(_or_payload(iat=now - 100, exp=now - 29))
    ).actor_type == "or"
    with pytest.raises(InvalidBearerToken):
        service.decode(_encode(_or_payload(iat=now + 31, exp=now + 60)))
    with pytest.raises(InvalidBearerToken):
        service.decode(_encode(_or_payload(iat=now - 100, exp=now - 31)))


def test_api_issued_profiles_are_exact_distinct_and_test_bound() -> None:
    service = TokenService(_settings())
    first = service.issue_player(TEST_ID)
    second = service.issue_player(TEST_ID)
    assert first != second
    player = service.decode(first)
    assert player.actor_type == "player"
    assert player.authorized_test_id == TEST_ID
    assert player.scopes == frozenset({TESTS_PLAY})
    assert service.player_url(TEST_ID, first) == (
        f"http://localhost:5173/test/{TEST_ID}#token={first}"
    )

    admin_token = service.issue_admin()
    admin = service.decode(admin_token)
    assert admin.actor_type == "admin"
    assert admin.subject == "development-admin"
    assert admin.scopes == ADMIN_SCOPES
    assert admin.scopes.isdisjoint({TESTS_CREATE, TESTS_PLAY})

    player_payload = cast(
        dict[str, object], jwt.decode(first, options={"verify_signature": False})
    )
    player_payload["test_id"] = str(UUID("20000000-0000-4000-8000-000000000002"))
    rebound = _encode(player_payload, secret=API_SECRET)
    with pytest.raises(InvalidBearerToken):
        service.decode(rebound)
    assert type(player_payload["iat"]) is int
    assert type(player_payload["exp"]) is int
    assert player_payload["exp"] - player_payload["iat"] == 28_800

    noncanonical_jti = dict(player_payload)
    noncanonical_jti["test_id"] = str(TEST_ID)
    noncanonical_jti["sub"] = f"player:{TEST_ID}"
    noncanonical_jti["jti"] = "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"
    with pytest.raises(InvalidBearerToken):
        service.decode(_encode(noncanonical_jti, secret=API_SECRET))


def test_secret_rotation_is_profile_independent() -> None:
    original = TokenService(_settings())
    player = original.issue_player(TEST_ID)
    or_token = _encode(_or_payload())
    api_rotated = TokenService(
        _settings(API_JWT_SECRET="rotated-api-secret-000000000000000000000000000")
    )
    with pytest.raises(InvalidBearerToken):
        api_rotated.decode(player)
    assert api_rotated.decode(or_token).actor_type == "or"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "ftp://example.com",
        "https://user@example.com",
        "https://example.com/player",
        "https://example.com?query=1",
        "https://example.com#fragment",
    ],
)
def test_player_app_url_rejects_non_origin_or_insecure_values(url: str) -> None:
    with pytest.raises(ValidationError):
        _settings(PLAYER_APP_URL=url)


def test_settings_reject_weak_missing_and_reused_secrets() -> None:
    with pytest.raises(ValidationError):
        _settings(OR_JWT_SECRET="short")
    with pytest.raises(ValidationError):
        _settings(API_JWT_SECRET=OR_SECRET)
