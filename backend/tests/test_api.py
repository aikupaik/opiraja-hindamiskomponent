"""FastAPI boundary and operational acceptance coverage."""

import json
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import UUID

import httpx
import jwt
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from supabase import AsyncClient as SupabaseAsyncClient
from supabase import AsyncClientOptions
from uvicorn._types import ASGI3Application
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.auth import (
    ADMIN_SIMULATION,
    TESTS_CREATE,
    TESTS_LAUNCH,
    TESTS_PLAY,
    TESTS_READ,
    AuthContext,
    AuthorizationDenied,
    authorize_player,
    require_or,
    require_player,
)
from app.api.dependencies import get_kst_engine, get_repository
from app.api.tokens import TokenService
from app.config import Settings
from app.domain.models import AdvanceCompleted, ItemId, ModelBuildResult, SessionStatus
from app.domain.repository import AssessmentRepository
from app.domain.repository import RepositoryUnavailable
from app.integrations.kst_engine import KstEngine
from app.main import build_lifespan, create_app
from app.services.assessment import AssessmentService
from tests.factories import (
    SUBMISSION_ID,
    TEST_ID,
    make_item,
    make_model,
    make_profile,
    make_session,
)
from tests.fakes.assessment_repository import InMemoryAssessmentRepository
from tests.fakes.kst_engine import FakeKstEngine


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_KEY": "super-secret-service-key",
            "R_SERVICE_URL": "http://r-service:8000",
            "ALLOWED_HOSTS": ["193.40.157.124", "127.0.0.1", "testserver"],
            "READINESS_TIMEOUT_SECONDS": 0.05,
            "OR_JWT_SECRET": "or-test-secret-00000000000000000000000000000000",
            "API_JWT_SECRET": "api-test-secret-0000000000000000000000000000000",
            "OR_JWT_ISSUER": "test-or",
            "PLAYER_APP_URL": "http://localhost:5173",
        }
    )


def _or_token(*scopes: str) -> str:
    now = int(time.time())
    granted = scopes or (TESTS_CREATE, TESTS_READ, TESTS_LAUNCH)
    settings = _settings()
    return jwt.encode(
        {
            "iss": settings.or_jwt_issuer,
            "aud": "assessment-api",
            "sub": "test-or-service",
            "scope": " ".join(granted),
            "iat": now,
            "exp": now + 300,
        },
        settings.or_jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def _player_token(test_id: UUID) -> str:
    return TokenService(_settings()).issue_player(test_id)


def _admin_token() -> str:
    return TokenService(_settings()).issue_admin()


def _authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_simulation_is_an_explicit_cross_profile_exception() -> None:
    test_id = UUID("10000000-0000-4000-8000-000000000001")
    admin = AuthContext(
        actor_type="admin",
        subject="operator",
        scopes=frozenset({ADMIN_SIMULATION}),
    )
    admin_without_simulation = AuthContext(
        actor_type="admin",
        subject="read-only-operator",
        scopes=frozenset(),
    )
    or_context = AuthContext(
        actor_type="or",
        subject="or-service",
        scopes=frozenset({TESTS_CREATE}),
    )
    player_context = AuthContext(
        actor_type="player",
        subject="player",
        scopes=frozenset({TESTS_PLAY}),
        authorized_test_id=test_id,
    )

    require_or(or_context, TESTS_CREATE)
    require_player(player_context, test_id)
    require_or(admin, TESTS_CREATE, allow_admin_simulation=True)
    require_player(admin, test_id, allow_admin_simulation=True)

    with pytest.raises(AuthorizationDenied):
        require_or(admin, TESTS_CREATE)
    with pytest.raises(AuthorizationDenied):
        require_player(admin, test_id)
    with pytest.raises(AuthorizationDenied):
        require_or(admin_without_simulation, TESTS_CREATE, allow_admin_simulation=True)
    with pytest.raises(AuthorizationDenied):
        require_player(
            admin_without_simulation, test_id, allow_admin_simulation=True
        )
    with pytest.raises(AuthorizationDenied):
        require_player(or_context, test_id, allow_admin_simulation=True)
    with pytest.raises(AuthorizationDenied):
        require_or(player_context, TESTS_CREATE, allow_admin_simulation=True)


def _app(
    repository: InMemoryAssessmentRepository,
    engine: FakeKstEngine,
    *,
    seed_active: bool = False,
) -> FastAPI:
    settings = _settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        if seed_active:
            await repository.seed_session(make_session())
            await repository.seed_items(make_item())
        app.state.repository = repository
        app.state.kst_engine = engine
        app.state.assessment_service = AssessmentService(
            repository,
            engine,
            max_graph_nodes=settings.max_graph_nodes,
        )
        yield

    return create_app(settings, lifespan=lifespan)


async def _request_context(request: Request) -> JSONResponse:
    client = request.client
    return JSONResponse(
        {
            "scheme": request.url.scheme,
            "client": None if client is None else client.host,
        }
    )


@asynccontextmanager
async def _client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client


@pytest.mark.asyncio
async def test_liveness_is_dependency_free_and_readiness_is_bounded() -> None:
    repository = InMemoryAssessmentRepository()
    engine = FakeKstEngine(ready=False)

    async with _client(_app(repository, engine)) as client:
        live = await client.get("/health/live")
        assert live.status_code == 200
        assert live.json() == {"status": "ok"}
        assert repository.calls == ()
        assert engine.calls == ()

        ready = await client.get("/health/ready")

    assert ready.status_code == 503
    assert ready.json() == {
        "status": "unavailable",
        "dependencies": {"supabase": "ready", "r": "unavailable"},
    }


@pytest.mark.asyncio
async def test_trusted_hosts_allow_phase_hosts_and_reject_arbitrary_host() -> None:
    app = _app(InMemoryAssessmentRepository(), FakeKstEngine())

    async with _client(app) as client:
        for host in ("193.40.157.124", "127.0.0.1"):
            response = await client.get(
                "/health/live",
                headers={"Host": host},
            )
            assert response.status_code == 200

        rejected = await client.get(
            "/health/live",
            headers={"Host": "unapproved.example"},
        )

    assert rejected.status_code == 400


@pytest.mark.asyncio
async def test_proxy_headers_preserve_https_and_original_client_only_from_trusted_proxy() -> None:
    app = _app(InMemoryAssessmentRepository(), FakeKstEngine())
    app.add_api_route("/__test/request-context", _request_context)
    proxy_app = ProxyHeadersMiddleware(
        cast(ASGI3Application, app), trusted_hosts="172.30.0.0/24"
    )

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=cast(Any, proxy_app),
                client=("172.30.0.10", 8080),
            ),
            base_url="http://193.40.157.124",
        ) as client:
            through_proxies = await client.get(
                "/__test/request-context",
                headers={
                    "Host": "193.40.157.124",
                    "X-Forwarded-Proto": "https",
                    "X-Forwarded-For": "198.51.100.24, 172.30.0.5",
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=cast(Any, proxy_app),
                client=("198.51.100.25", 8080),
            ),
            base_url="http://193.40.157.124",
        ) as client:
            from_untrusted_peer = await client.get(
                "/__test/request-context",
                headers={
                    "Host": "193.40.157.124",
                    "X-Forwarded-Proto": "https",
                    "X-Forwarded-For": "203.0.113.90",
                },
            )

    assert through_proxies.status_code == 200
    assert through_proxies.json() == {
        "scheme": "https",
        "client": "198.51.100.24",
    }
    assert from_untrusted_peer.status_code == 200
    assert from_untrusted_peer.json() == {
        "scheme": "http",
        "client": "198.51.100.25",
    }


@pytest.mark.asyncio
async def test_create_preparing_get_and_player_poll_have_exact_public_shapes() -> None:
    repository = InMemoryAssessmentRepository()
    model = make_model()
    app = _app(
        repository,
        FakeKstEngine(
            model_results=(
                ModelBuildResult(model=model, posterior=model.uniform_prior),
            )
        ),
    )

    async with _client(app) as client:
        created = await client.post(
            "/api/v1/tests",
            headers=_authorization(_or_token()),
            json={
                "user_id": "or-user",
                "learning_path_id": "path-1",
                "nodes": ["B", "A"],
                "relations": [{"from": "A", "to": "B"}],
                "goal": "Understand the graph",
            },
        )
        assert created.status_code == 201
        body = created.json()
        test_id = UUID(body["test_id"])
        assert body == {
            "test_id": str(test_id),
            "status": "preparing",
            "player_url": body["player_url"],
            "missing_nodes": ["A", "B"],
        }
        assert body["player_url"].startswith(
            f"http://localhost:5173/test/{test_id}#token="
        )
        player_token = body["player_url"].split("#token=", 1)[1]
        assert created.headers["cache-control"] == "no-store"
        assert created.headers["location"] == f"/api/v1/tests/{test_id}"

        status_response = await client.get(
            f"/api/v1/tests/{test_id}", headers=_authorization(_or_token())
        )
        assert status_response.status_code == 200
        assert status_response.json() == {"status": "preparing"}

        player = await client.post(
            f"/api/v1/player/tests/{test_id}/start",
            headers=_authorization(player_token),
        )
        assert player.status_code == 202
        assert player.headers["retry-after"] == "3"
        assert player.json() == {"status": "preparing"}

        invalid = await client.post(
            "/api/v1/tests",
            headers=_authorization(_or_token()),
            json={
                "user_id": "or-user",
                "learning_path_id": "path-1",
                "nodes": ["A"],
                "relations": [],
                "unexpected": True,
            },
        )
        assert invalid.status_code == 422
        assert "detail" in invalid.json()

        invalid_graph = await client.post(
            "/api/v1/tests",
            headers=_authorization(_or_token()),
            json={
                "user_id": "or-user",
                "learning_path_id": "path-1",
                "nodes": ["A", "A"],
                "relations": [],
            },
        )
        assert invalid_graph.status_code == 422
        assert invalid_graph.json() == {
            "error": {
                "code": "invalid_graph",
                "message": "Graph is invalid.",
            }
        }


def test_public_assessment_openapi_matches_response_contract() -> None:
    schema = _app(InMemoryAssessmentRepository(), FakeKstEngine()).openapi()
    paths = cast(dict[str, Any], schema["paths"])
    operations = {
        "create": paths["/api/v1/tests"]["post"],
        "status": paths["/api/v1/tests/{test_id}"]["get"],
        "link": paths["/api/v1/tests/{test_id}/player-token"]["post"],
        "start": paths["/api/v1/player/tests/{test_id}/start"]["post"],
        "answer": paths["/api/v1/player/tests/{test_id}/answers"]["post"],
    }

    assert set(operations["create"]["responses"]) == {
        "201",
        "401",
        "403",
        "422",
        "500",
        "503",
    }
    assert set(operations["status"]["responses"]) == {
        "200",
        "401",
        "403",
        "404",
        "409",
        "422",
        "500",
        "503",
    }
    assert set(operations["start"]["responses"]) == {
        "200",
        "202",
        "401",
        "403",
        "404",
        "409",
        "422",
        "500",
        "503",
    }
    assert set(operations["link"]["responses"]) == {
        "200",
        "401",
        "403",
        "404",
        "409",
        "422",
        "500",
        "503",
    }
    assert set(operations["answer"]["responses"]) == {
        "200",
        "401",
        "403",
        "404",
        "409",
        "422",
        "500",
        "503",
    }
    for operation in operations.values():
        assert operation["security"] == [{"HTTPBearer": []}]

    start_success = operations["start"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["anyOf"]
    assert {item["$ref"] for item in start_success} == {
        "#/components/schemas/PlayerActiveResponse",
        "#/components/schemas/PlayerCompletedResponse",
    }
    assert operations["start"]["responses"]["202"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PlayerPreparingResponse"}

    create_validation = operations["create"]["responses"]["422"]["content"][
        "application/json"
    ]["schema"]["anyOf"]
    assert {item["$ref"] for item in create_validation} == {
        "#/components/schemas/RequestValidationResponse",
        "#/components/schemas/ErrorResponse",
    }


@pytest.mark.asyncio
async def test_player_completion_exposes_only_public_question_results() -> None:
    repository = InMemoryAssessmentRepository()
    engine = FakeKstEngine(
        advance_results=(AdvanceCompleted((0.1, 0.2, 0.7), make_profile()),)
    )

    async with _client(_app(repository, engine, seed_active=True)) as client:
        player_headers = _authorization(_player_token(UUID(str(TEST_ID))))
        started = await client.post(
            f"/api/v1/player/tests/{TEST_ID}/start", headers=player_headers
        )
        assert started.status_code == 200
        question = started.json()
        assert question == {
            "status": "active",
            "question": {
                "submission_id": str(SUBMISSION_ID),
                "item_id": 41,
                "instruction": "Choose one.",
                "prompt": "What is A?",
                "stimulus": None,
                "options": [
                    {"id": "option-1", "text": "Correct"},
                    {"id": "option-2", "text": "Wrong"},
                ],
            },
        }
        serialized = json.dumps(question)
        for hidden in (
            "answer_key",
            "correct_option_id",
            "candidate_id",
            "session_pool",
            "node",
            "posterior",
            "beta",
            "eta",
        ):
            assert hidden not in serialized

        completed = await client.post(
            f"/api/v1/player/tests/{TEST_ID}/answers",
            headers=player_headers,
            json={
                "submission_id": str(SUBMISSION_ID),
                "option_id": "option-1",
            },
        )
        assert completed.status_code == 200
        assert completed.json() == {
            "status": "completed",
            "feedback": {
                "already_mastered": ["A"],
                "learn_next": ["B"],
                "review": [],
                "summary": None,
                "confidence_limited": False,
            },
            "question_results": [
                {
                    "item_id": 41,
                    "prompt": "What is A?",
                    "stimulus": None,
                    "student_answer": "Correct",
                    "correct_answer": "Correct",
                    "is_correct": True,
                }
            ],
        }

        or_view = await client.get(
            f"/api/v1/tests/{TEST_ID}", headers=_authorization(_or_token())
        )
        assert or_view.json() == {
            "status": "completed",
            "feedback": completed.json()["feedback"],
        }


@pytest.mark.asyncio
async def test_authorization_override_and_stable_error_mapping_are_independent() -> None:
    repository = InMemoryAssessmentRepository()
    app = _app(repository, FakeKstEngine())

    async def wrong_player() -> AuthContext:
        return AuthContext(
            actor_type="player",
            subject="wrong-player",
            scopes=frozenset({TESTS_PLAY}),
            authorized_test_id=UUID("30000000-0000-4000-8000-000000000003"),
        )

    app.dependency_overrides[authorize_player] = wrong_player
    async with _client(app) as client:
        forbidden = await client.post(f"/api/v1/player/tests/{TEST_ID}/start")
        assert forbidden.status_code == 403
        assert forbidden.json() == {
            "error": {
                "code": "forbidden",
                "message": "Operation is not authorized.",
            }
        }

        missing = await client.get(
            f"/api/v1/tests/{TEST_ID}", headers=_authorization(_or_token())
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "assessment_not_found"

    repository.fail_next(
        "get_session", RepositoryUnavailable("contains super-secret-service-key")
    )
    app.dependency_overrides.clear()
    async with _client(app) as client:
        unavailable = await client.get(
            f"/api/v1/tests/{TEST_ID}", headers=_authorization(_or_token())
        )
        assert unavailable.status_code == 503
        assert unavailable.json() == {
            "error": {
                "code": "supabase_unavailable",
                "message": "Persistence service is unavailable.",
            }
        }
        assert "super-secret-service-key" not in unavailable.text


@pytest.mark.asyncio
async def test_request_id_completion_event_and_redaction(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = InMemoryAssessmentRepository()
    caplog.set_level(logging.INFO, logger="app.requests")

    async with _client(_app(repository, FakeKstEngine())) as client:
        response = await client.get(
            f"/api/v1/tests/{TEST_ID}",
            headers={
                "X-Request-ID": "request.safe-123",
                "Authorization": f"Bearer {_or_token()}",
            },
        )

    assert response.headers["x-request-id"] == "request.safe-123"
    messages = [
        record.getMessage()
        for record in caplog.records
        if '"event":"request_completed"' in record.getMessage()
    ]
    assert len(messages) == 1
    event = cast(dict[str, object], json.loads(messages[0]))
    assert event["request_id"] == "request.safe-123"
    assert event["test_id"] == str(TEST_ID)
    assert event["status"] == 404
    assert event["outcome"] == "assessment_not_found"
    assert event["supabase_execute_count"] == 0
    assert event["r_request_count"] == 0
    assert _or_token() not in messages[0]
    assert "super-secret-service-key" not in messages[0]


@pytest.mark.asyncio
async def test_persistence_and_r_dependencies_can_be_overridden_independently() -> None:
    state_repository = InMemoryAssessmentRepository()
    override_repository = InMemoryAssessmentRepository()
    await override_repository.seed_session(make_session())
    app = _app(state_repository, FakeKstEngine())

    def repository_override() -> AssessmentRepository:
        return override_repository

    app.dependency_overrides[get_repository] = repository_override
    async with _client(app) as client:
        response = await client.get(
            f"/api/v1/tests/{TEST_ID}", headers=_authorization(_or_token())
        )
    assert response.json() == {"status": "active"}

    app.dependency_overrides.clear()
    await state_repository.seed_items(
        *(make_item(ItemId(value), node="A") for value in range(1, 5)),
        *(make_item(ItemId(value), node="B") for value in range(11, 15)),
    )
    override_engine = FakeKstEngine(
        model_results=(
            ModelBuildResult(
                model=make_model(),
                posterior=make_model().uniform_prior,
            ),
        )
    )

    def engine_override() -> KstEngine:
        return override_engine

    app.dependency_overrides[get_kst_engine] = engine_override
    async with _client(app) as client:
        created = await client.post(
            "/api/v1/tests",
            headers=_authorization(_or_token()),
            json={
                "user_id": "or-user",
                "learning_path_id": "path-1",
                "nodes": ["A", "B"],
                "relations": [{"from": "A", "to": "B"}],
            },
        )
    assert created.status_code == 201
    assert created.json()["status"] == "active"
    assert [call.method for call in override_engine.calls] == [
        "build_model",
        "select",
    ]


@pytest.mark.asyncio
async def test_signed_profiles_have_generic_401_and_cross_profile_403() -> None:
    repository = InMemoryAssessmentRepository()
    await repository.seed_session(make_session())
    app = _app(repository, FakeKstEngine())
    wrong_test = UUID("30000000-0000-4000-8000-000000000003")

    async with _client(app) as client:
        for headers in ({}, {"Authorization": "Basic opaque"}, {"Authorization": "Bearer bad"}):
            response = await client.get(f"/api/v1/tests/{TEST_ID}", headers=headers)
            assert response.status_code == 401
            assert response.headers["www-authenticate"] == "Bearer"
            assert response.json() == {
                "error": {
                    "code": "invalid_token",
                    "message": "Valid bearer credentials are required.",
                }
            }

        player_on_or = await client.get(
            f"/api/v1/tests/{TEST_ID}",
            headers=_authorization(_player_token(UUID(str(TEST_ID)))),
        )
        or_on_player = await client.post(
            f"/api/v1/player/tests/{TEST_ID}/start",
            headers=_authorization(_or_token(TESTS_READ)),
        )
        wrong_binding = await client.post(
            f"/api/v1/player/tests/{TEST_ID}/start",
            headers=_authorization(_player_token(wrong_test)),
        )

    assert player_on_or.status_code == 403
    assert or_on_player.status_code == 403
    assert wrong_binding.status_code == 403


@pytest.mark.asyncio
async def test_player_token_route_is_fresh_no_store_and_strictly_or_launch() -> None:
    repository = InMemoryAssessmentRepository()
    await repository.seed_session(make_session())
    app = _app(repository, FakeKstEngine())
    path = f"/api/v1/tests/{TEST_ID}/player-token"

    async with _client(app) as client:
        first = await client.post(
            path, headers=_authorization(_or_token(TESTS_LAUNCH))
        )
        second = await client.post(
            path, headers=_authorization(_or_token(TESTS_LAUNCH))
        )
        insufficient = await client.post(
            path, headers=_authorization(_or_token(TESTS_READ))
        )
        admin = await client.post(path, headers=_authorization(_admin_token()))
        unknown = await client.post(
            "/api/v1/tests/30000000-0000-4000-8000-000000000003/player-token",
            headers=_authorization(_or_token(TESTS_LAUNCH)),
        )

    assert first.status_code == second.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    assert first.json()["player_url"].startswith(
        f"http://localhost:5173/test/{TEST_ID}#token="
    )
    assert first.json() != second.json()
    assert insufficient.status_code == 403
    assert admin.status_code == 403
    assert unknown.status_code == 404

    failed_repository = InMemoryAssessmentRepository()
    await failed_repository.seed_session(make_session(status=SessionStatus.FAILED))
    async with _client(_app(failed_repository, FakeKstEngine())) as client:
        failed = await client.post(
            path, headers=_authorization(_or_token(TESTS_LAUNCH))
        )
    assert failed.status_code == 409


@pytest.mark.asyncio
async def test_default_lifespan_closes_all_owned_http_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clients: list[_FakeManagedHttpClient] = []

    def make_http_client(**options: object) -> httpx.AsyncClient:
        client = _FakeManagedHttpClient(options)
        clients.append(client)
        return cast(httpx.AsyncClient, client)

    async def make_supabase_client(
        _url: str,
        _key: str,
        options: AsyncClientOptions | None = None,
    ) -> SupabaseAsyncClient:
        assert options is not None
        return cast(SupabaseAsyncClient, object())

    monkeypatch.setattr("app.main.httpx.AsyncClient", make_http_client)
    monkeypatch.setattr("app.main.acreate_client", make_supabase_client)
    app = FastAPI()

    async with build_lifespan(_settings())(app):
        assert len(clients) == 3
        assert not any(client.closed for client in clients)
        assert isinstance(app.state.assessment_service, AssessmentService)

    assert all(client.closed for client in clients)
    r_options = clients[1].options
    assert isinstance(r_options["timeout"], httpx.Timeout)
    assert isinstance(r_options["limits"], httpx.Limits)


class _FakeManagedHttpClient:
    def __init__(self, options: dict[str, object]) -> None:
        self.options = options
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True
