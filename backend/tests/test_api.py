"""FastAPI boundary and operational acceptance coverage."""

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from supabase import AsyncClient as SupabaseAsyncClient
from supabase import AsyncClientOptions

from app.api.auth import AuthContext, authorize_player
from app.api.dependencies import get_kst_engine, get_repository
from app.config import Settings
from app.domain.models import AdvanceCompleted, ItemId, ModelBuildResult
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
            "READINESS_TIMEOUT_SECONDS": 0.05,
        }
    )


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
            "player_url": f"/test/{test_id}",
            "missing_nodes": ["A", "B"],
        }
        assert created.headers["location"] == f"/api/v1/tests/{test_id}"

        status_response = await client.get(f"/api/v1/tests/{test_id}")
        assert status_response.status_code == 200
        assert status_response.json() == {"status": "preparing"}

        player = await client.post(f"/api/v1/player/tests/{test_id}/start")
        assert player.status_code == 202
        assert player.headers["retry-after"] == "3"
        assert player.json() == {"status": "preparing"}

        invalid = await client.post(
            "/api/v1/tests",
            json={
                "user_id": "or-user",
                "learning_path_id": "path-1",
                "nodes": ["A"],
                "relations": [],
                "unexpected": True,
            },
        )
        assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_player_start_and_completion_never_expose_internal_assessment_data() -> None:
    repository = InMemoryAssessmentRepository()
    engine = FakeKstEngine(
        advance_results=(AdvanceCompleted((0.1, 0.2, 0.7), make_profile()),)
    )

    async with _client(_app(repository, engine, seed_active=True)) as client:
        started = await client.post(f"/api/v1/player/tests/{TEST_ID}/start")
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
        }

        or_view = await client.get(f"/api/v1/tests/{TEST_ID}")
        assert or_view.json() == completed.json()


@pytest.mark.asyncio
async def test_authorization_override_and_stable_error_mapping_are_independent() -> None:
    repository = InMemoryAssessmentRepository()
    app = _app(repository, FakeKstEngine())

    async def wrong_player() -> AuthContext:
        return AuthContext(
            actor_type="player",
            subject="wrong-player",
            scopes=frozenset({"tests:play"}),
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

        missing = await client.get(f"/api/v1/tests/{TEST_ID}")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "assessment_not_found"

    repository.fail_next(
        "get_session", RepositoryUnavailable("contains super-secret-service-key")
    )
    app.dependency_overrides.clear()
    async with _client(app) as client:
        unavailable = await client.get(f"/api/v1/tests/{TEST_ID}")
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
                "Authorization": "Bearer player-secret",
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
    assert "player-secret" not in messages[0]
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
        response = await client.get(f"/api/v1/tests/{TEST_ID}")
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
